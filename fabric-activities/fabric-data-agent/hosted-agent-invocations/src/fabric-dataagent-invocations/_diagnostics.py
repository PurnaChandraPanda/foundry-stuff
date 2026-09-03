"""Reusable, opt-in diagnostics for Foundry hosted agents.

Drop this file next to main.py and hook in as much or as little as you need.
Every hook is a **no-op while disabled**, so the hooks can be left in the
shipping code permanently and switched on with an env var when a deployed
container misbehaves.

Enable:
    AGENT_DIAG_PROBE=1          # off by default
    AGENT_DIAG_INTERVAL=60      # seconds between probe cycles
    AGENT_DIAG_STDOUT=0         # stderr only - required for stdio MCP servers
    AGENT_DIAG_EGRESS=a.com,b.com   # override the egress probe's host list

Reuse outside a Foundry agent
-----------------------------
The core - emit/register_probe/run_once/start/probe_egress/install_asgi - is
host-agnostic and depends only on the stdlib. Use it in an MCP server, a
Logic App custom connector, a DevOps tool, or any long-running worker::

    from _diagnostics import diagnostics

    diagnostics.configure(enabled=True)
    diagnostics.unregister_probe("identity")     # Azure-only, skips anyway
    diagnostics.unregister_probe("connection")   # Azure-only, skips anyway
    diagnostics.check_egress("dev.azure.com", "api.github.com")
    diagnostics.start()

Two host-specific notes:

* **stdio MCP servers**: pass ``use_stdout=False``. The MCP spec requires that
  a server write nothing to stdout that is not a JSON-RPC message, so a stray
  diagnostic line breaks the transport. stderr is explicitly allowed for logs.
* **Optional dependencies**: only ``call_arm``/``probe_connection_access`` need
  httpx, ``agent_middlewares()`` needs agent_framework, and ``log_request``
  needs a Starlette-style request. All three are imported lazily, so the rest
  of the module works without them.

``install_asgi(app)`` works with any ASGI app (Starlette, FastAPI, FastMCP's
Streamable HTTP app), not just the Foundry hosts.

Minimal wiring (any protocol)::

    from _diagnostics import diagnostics

    diagnostics.configure(credential=_credential)
    diagnostics.start()                       # repeating background probe

Optional extra hooks::

    diagnostics.set_context(fabric_tool=json.dumps(fabric_tool))
    diagnostics.install_asgi(app)             # log every HTTP request
    Agent(..., middleware=diagnostics.agent_middlewares())   # Responses
    diagnostics.log_request(request)          # Invocations handler

Add your own probe without touching this file::

    @diagnostics.probe("fabric-workspace")
    def _check() -> None:
        resp = diagnostics.call_arm(f"{PROJECT_ID}/connections", method="GET")
        diagnostics.emit(f"connections -> {resp.status_code}")

Built-in probes, all running every cycle once enabled:

* ``identity``   - decodes the container's own token claims (oid/appid/tenant)
* ``connection`` - listSecrets at project and account scope
* ``egress``     - DNS + TCP + TLS on 443 to login.microsoftonline.com,
  management.azure.com, this project's Foundry endpoint and
  api.fabric.microsoft.com

Override the egress host list without touching this file, either with
``AGENT_DIAG_EGRESS`` (comma-separated) or::

    diagnostics.check_egress("management.azure.com", "api.fabric.microsoft.com")

Why the design looks like this
------------------------------
* Probes run on a **repeating timer**, not once at startup, because
  ``azd ai agent monitor`` attaches to an already-running container and would
  miss a one-shot line.
* ``start()`` is meant to be called from a function the runtime actually
  executes (e.g. ``build_agent()``), **not** from ``main()``. With
  ``dependencyResolution: remote_build`` the hosting runtime imports the module
  and supplies its own launcher, so ``main()`` never runs in the container and
  anything started there is dead code.
* Output goes to stdout *and* stderr - see ``emit``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx

__all__ = ["Diagnostics", "diagnostics"]

ARM_SCOPE = "https://management.azure.com/.default"
FOUNDRY_SCOPE = "https://ai.azure.com/.default"
ARM_BASE = "https://management.azure.com"

# Distinctive prefix so diagnostics can be grepped out of the trace JSON, which
# is orders of magnitude larger than they are.
# Default grep prefix. Distinctive so diagnostics can be pulled out of the trace
# JSON, which is orders of magnitude larger than they are. Override per-instance
# with configure(prefix=...).
DIAG_PREFIX = "AGENTDIAG |"

_DEFAULT_API_VERSION = "2025-04-01-preview"

# curl exit codes worth naming. A blocked egress almost always shows up as 28
# (the packets are dropped, so the connection just times out) rather than 7.
_CURL_ERRORS = {
    6: "DNS resolution failed",
    7: "connection refused/unreachable",
    28: "timed out - egress likely blocked",
    35: "TLS handshake failed - inspect proxy?",
    60: "TLS certificate not trusted - inspect proxy?",
}


def _env_flag(name: str, default: str) -> bool:
    return os.environ.get(name, default) not in ("0", "false", "False", "")


class Diagnostics:
    """Container for probes, hooks and their shared configuration.

    A module-level singleton (``diagnostics``) is provided; construct your own
    only if you need two independently configured sets of probes.
    """

    def __init__(self) -> None:
        self.enabled: bool = _env_flag("AGENT_DIAG_PROBE", "0")
        self.interval_seconds: int = int(os.environ.get("AGENT_DIAG_INTERVAL", "60"))
        self.credential: Any = None
        self.project_id: str | None = os.environ.get("AZURE_AI_PROJECT_ID")
        self.project_endpoint: str | None = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        self.connection_name: str | None = os.environ.get("FABRIC_CONNECTION_NAME")
        self.api_version: str = _DEFAULT_API_VERSION
        self.logger = logging.getLogger("agent-diagnostics")
        self.prefix: str = DIAG_PREFIX

        # Whether emit() also writes to stdout. Must be False in a **stdio MCP
        # server**: the MCP spec says the server "MUST NOT write anything to its
        # stdout that is not a valid MCP message", so a stray diagnostic line
        # corrupts the JSON-RPC framing and the client drops the connection.
        # stderr is explicitly allowed for logging, so the logger copy is safe.
        self.use_stdout: bool = _env_flag("AGENT_DIAG_STDOUT", "1")

        # Hosts for the default egress probe. None means "derive at run time"
        # (see default_egress_hosts), so a later configure(project_endpoint=...)
        # is still picked up. Override with AGENT_DIAG_EGRESS as a comma-
        # separated list, or with check_egress(...).
        env_hosts = os.environ.get("AGENT_DIAG_EGRESS", "").strip()
        self.egress_hosts: list[str] | None = (
            [h.strip() for h in env_hosts.split(",") if h.strip()] or None
            if env_hosts
            else None
        )

        # Arbitrary key/values echoed on every probe cycle. Use for values only
        # known at build time, e.g. the serialized tool payload.
        self._context: dict[str, str] = {}

        self._probes: dict[str, Callable[[], None]] = {}
        self._started = False
        self._lock = threading.Lock()

        self.register_probe("identity", self.probe_token_identity)
        self.register_probe("connection", self.probe_connection_access)
        # On by default: a blocked egress and a rejected token surface as the
        # same opaque server-side error, so this is worth ruling out first.
        self.register_probe("egress", self._default_egress_probe)

    # -- configuration -----------------------------------------------------

    def configure(
        self,
        *,
        credential: Any = None,
        project_id: str | None = None,
        project_endpoint: str | None = None,
        connection_name: str | None = None,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        api_version: str | None = None,
        logger: logging.Logger | None = None,
        prefix: str | None = None,
        use_stdout: bool | None = None,
        egress_hosts: list[str] | None = None,
    ) -> Diagnostics:
        """Set what the built-in probes need. Every argument is optional.

        Unset values fall back to the environment, so passing only
        ``credential`` is usually enough. Returns self so calls can be chained.
        """
        if credential is not None:
            self.credential = credential
        if project_id is not None:
            self.project_id = project_id
        if project_endpoint is not None:
            self.project_endpoint = project_endpoint
        if connection_name is not None:
            self.connection_name = connection_name
        if enabled is not None:
            self.enabled = enabled
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        if api_version is not None:
            self.api_version = api_version
        if logger is not None:
            self.logger = logger
        if prefix is not None:
            self.prefix = prefix
        if use_stdout is not None:
            self.use_stdout = use_stdout
        if egress_hosts is not None:
            self.egress_hosts = egress_hosts
        return self

    def set_context(self, **fields: Any) -> None:
        """Record values to echo on every probe cycle.

        Useful for things only known once the agent is built - the serialized
        Fabric tool payload, the resolved connection id - so they appear in a
        capture taken long after startup.
        """
        for key, value in fields.items():
            self._context[key] = value if isinstance(value, str) else repr(value)

    # -- output ------------------------------------------------------------

    def emit(self, message: str) -> None:
        """Write one diagnostic line to stderr, and to stdout unless disabled.

        These are different destinations: ``print`` goes to stdout, while
        ``logging.basicConfig`` attaches a StreamHandler on **stderr**. Which
        one a hosted log collector scrapes is not documented, so write both and
        let whichever is captured win; the logger copy is identifiable by its
        ``INFO:agent-diagnostics:`` prefix.

        Set ``use_stdout=False`` (or ``AGENT_DIAG_STDOUT=0``) when stdout is a
        protocol channel rather than a log - a **stdio MCP server** is the case
        that matters, since anything on stdout that is not a JSON-RPC message
        breaks the transport. stderr remains valid for logging there.

        ``flush=True`` is required, not cosmetic: when stdout is a pipe rather
        than a TTY - i.e. any container - Python block-buffers it (~8 KB), so an
        unflushed line can sit in the buffer and never be written. stderr stays
        line-buffered, so the logger copy is not affected.
        """
        if self.use_stdout:
            print(f"{self.prefix} {message}", flush=True)
        self.logger.info("%s %s", self.prefix, message)

    # -- reusable building blocks for custom probes ------------------------

    def token_claims(self, scope: str = FOUNDRY_SCOPE) -> dict[str, Any]:
        """Decode the JWT this process would send for ``scope``.

        Decoded locally, with no service call, so it still works when every
        outbound authorization is failing.
        """
        if self.credential is None:
            raise RuntimeError("diagnostics.configure(credential=...) not called")
        token = self.credential.get_token(scope).token
        payload = token.split(".")[1]  # JWT payload is the middle segment
        payload += "=" * (-len(payload) % 4)  # base64url, padding stripped
        return json.loads(base64.urlsafe_b64decode(payload))

    def call_arm(
        self,
        resource_path: str,
        *,
        method: str = "POST",
        api_version: str | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> httpx.Response:
        """Call ARM with the current credential. For building custom probes.

        ``resource_path`` is an ARM resource id (leading slash, no host).

        httpx is imported here rather than at module scope so a host that only
        wants emit()/egress/custom probes can use this file without it.
        """
        import httpx

        if self.credential is None:
            raise RuntimeError("diagnostics.configure(credential=...) not called")
        token = self.credential.get_token(ARM_SCOPE).token
        url = f"{ARM_BASE}{resource_path}?api-version={api_version or self.api_version}"
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        return httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)

    def scopes(self) -> list[tuple[str, str]]:
        """Return ``[("project", <id>), ("account", <id>)]`` for the project.

        Account scope is the project id with the trailing ``/projects/<name>``
        removed. Both are worth probing because they are granted by different
        roles and a caller can hold one without the other.
        """
        if not self.project_id:
            return []
        # NOTE: must stay a *list of tuples*. `(("project", x))` is not a
        # 1-tuple - it iterates the inner tuple and unpacks the string
        # "project" into two names, raising "too many values to unpack".
        return [
            ("project", self.project_id),
            ("account", self.project_id.split("/projects/")[0]),
        ]

    # -- built-in probes ---------------------------------------------------

    def probe_token_identity(self) -> None:
        """Log which identity this container authenticates as.

        ``oid`` is what ``az role assignment create --assignee-object-id``
        expects; ``idtyp=app`` confirms a service principal rather than a user.

        Skips rather than raises when no credential is configured, so this file
        stays usable in a non-Azure host without unregistering the probe.
        """
        if self.credential is None:
            self.emit("identity: skipped, no credential configured")
            return
        claims = self.token_claims()
        self.emit(
            "identity: oid={} appid={} idtyp={} tid={}".format(
                claims.get("oid"),
                claims.get("appid"),
                claims.get("idtyp"),
                claims.get("tid"),
            )
        )

    def probe_connection_access(self) -> None:
        """Check whether this identity can read the connection's secrets.

        Emits the raw status and body so an ``AuthorizationFailed`` names the
        exact action and scope that is missing.
        """
        if not self.project_id or not self.connection_name:
            self.emit("connection: skipped, project_id/connection_name not set")
            return
        for scope, base in self.scopes():
            resp = self.call_arm(
                f"{base}/connections/{self.connection_name}/listSecrets"
            )
            detail = "" if resp.status_code == 200 else f" body={resp.text[:400]}"
            self.emit(f"{scope} listSecrets -> {resp.status_code}{detail}")

    # -- egress / connectivity --------------------------------------------

    def probe_egress(
        self,
        fqdn: str,
        *,
        port: int = 443,
        timeout: float = 10.0,
        method: str = "auto",
    ) -> dict[str, Any]:
        """Test outbound TLS reachability to ``fqdn:port``. Never raises.

        Answers "can this container reach the internet at all, and this host in
        particular?" - the question to ask before blaming auth, because a
        blocked egress and a rejected token can surface as the same opaque
        server-side error.

        ``method``:
            ``"curl"``    shell out to curl; richest output (per-phase timings).
            ``"socket"``  stdlib DNS + TCP + TLS; no external binary needed.
            ``"auto"``    curl when it is on PATH, else socket. **Use this.**

        Slim Python base images usually do *not* ship curl, so a hard-coded
        ``"curl"`` can fail in the container while working on your laptop.

        :return: ``{"host", "port", "ok", "via", "detail"}``. Also emitted.
        """
        chosen = method
        if method == "auto":
            chosen = "curl" if shutil.which("curl") else "socket"

        try:
            if chosen == "curl":
                ok, detail = self._egress_via_curl(fqdn, port, timeout)
            else:
                ok, detail = self._egress_via_socket(fqdn, port, timeout)
        except Exception as exc:
            ok, detail = False, f"probe error {type(exc).__name__}: {exc}"

        self.emit(
            f"egress {fqdn}:{port} -> {'OK' if ok else 'FAIL'} "
            f"via {chosen} {detail}"
        )
        return {"host": fqdn, "port": port, "ok": ok, "via": chosen, "detail": detail}

    def _egress_via_curl(
        self, fqdn: str, port: int, timeout: float
    ) -> tuple[bool, str]:
        """Run curl and report per-phase timings, or a named failure.

        The -w timings split the attempt into DNS / TCP / TLS, which localises a
        failure far better than a single "it didn't work": a stalled
        ``time_appconnect`` with a healthy ``time_connect`` points at TLS
        interception rather than a blocked port.

        ``src`` is the container's own NIC address, **not** the public address
        the destination sees - a hosted agent egresses through SNAT, so the two
        differ. ``dst`` is the address actually connected to, which is worth
        comparing against a Private Endpoint or firewall allowlist.
        """
        fmt = (
            "http=%{http_code} src=%{local_ip}:%{local_port} "
            "dst=%{remote_ip}:%{remote_port} "
            "dns=%{time_namelookup}s tcp=%{time_connect}s "
            "tls=%{time_appconnect}s total=%{time_total}s"
        )
        cmd = [
            "curl", "-sS",
            "-o", os.devnull,          # discard the body, keep the metrics
            "-w", fmt,
            "--max-time", str(int(timeout)),
            f"https://{fqdn}:{port}",
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            # Outlive curl's own --max-time so its exit code wins the race and
            # we get the named reason instead of a generic kill.
            out, err = proc.communicate(timeout=timeout + 5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            return False, f"curl did not exit within {timeout + 5}s"

        if proc.returncode == 0:
            # Any HTTP status means DNS + TCP + TLS all succeeded; a 400/401/404
            # from an unauthenticated probe still proves reachability.
            return True, out.strip()
        reason = _CURL_ERRORS.get(proc.returncode, "see stderr")
        return False, f"rc={proc.returncode} ({reason}) {err.strip()[:200]}"

    def _egress_via_socket(
        self, fqdn: str, port: int, timeout: float
    ) -> tuple[bool, str]:
        """DNS + TCP + TLS using only the stdlib, for images without curl.

        Each stage is attempted separately so the failing one is named, which is
        the whole point of the probe.
        """
        started = time.monotonic()
        try:
            addrs = socket.getaddrinfo(fqdn, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            return False, f"DNS resolution failed: {exc}"
        resolved = addrs[0][4][0]
        dns_ms = (time.monotonic() - started) * 1000

        ctx = ssl.create_default_context()
        try:
            with socket.create_connection((fqdn, port), timeout=timeout) as sock:
                tcp_ms = (time.monotonic() - started) * 1000 - dns_ms
                # Only meaningful once connected: the kernel picks the source
                # address as part of routing, so this also reveals which NIC
                # the traffic left by.
                local = sock.getsockname()
                peer = sock.getpeername()
                endpoints = f"src={local[0]}:{local[1]} dst={peer[0]}:{peer[1]}"
                with ctx.wrap_socket(sock, server_hostname=fqdn) as tls:
                    total_ms = (time.monotonic() - started) * 1000
                    return True, (
                        f"{endpoints} {tls.version()} "
                        f"dns={dns_ms:.0f}ms tcp={tcp_ms:.0f}ms total={total_ms:.0f}ms"
                    )
        except (TimeoutError, socket.timeout):
            return False, f"dst={resolved}:{port} TCP timed out - egress likely blocked"
        except ConnectionRefusedError:
            return False, f"dst={resolved}:{port} connection refused"
        except ssl.SSLCertVerificationError as exc:
            return False, (
                f"dst={resolved}:{port} TLS cert not trusted (inspect proxy?): {exc}"
            )
        except ssl.SSLError as exc:
            return False, f"dst={resolved}:{port} TLS handshake failed: {exc}"
        except OSError as exc:
            return False, f"dst={resolved}:{port} {type(exc).__name__}: {exc}"

    def default_egress_hosts(self) -> list[str]:
        """Hosts the default egress probe tests when none were given.

        Derived at call time rather than in ``__init__`` so a later
        ``configure(project_endpoint=...)`` is reflected. Covers the three legs
        a hosted agent depends on: token issuance, ARM (connection lookup) and
        Fabric itself, plus this project's own Foundry endpoint.
        """
        hosts = ["login.microsoftonline.com", "management.azure.com"]
        if self.project_endpoint:
            parsed = urlparse(self.project_endpoint)
            # Accept a bare host as well as a full URL.
            host = parsed.hostname or self.project_endpoint.split("/")[0]
            if host:
                hosts.append(host)
        hosts.append("api.fabric.microsoft.com")
        # dict.fromkeys de-duplicates while preserving order.
        return list(dict.fromkeys(hosts))

    def _default_egress_probe(self) -> None:
        """Registered by default; tests ``egress_hosts`` or the derived list."""
        for fqdn in self.egress_hosts or self.default_egress_hosts():
            self.probe_egress(fqdn)

    def check_egress(
        self,
        *fqdns: str,
        name: str = "egress",
        port: int = 443,
        timeout: float = 10.0,
        method: str = "auto",
    ) -> None:
        """Replace the default egress probe with an explicit host list.

        An ``egress`` probe is already registered by default, so call this only
        to narrow or extend what it tests - it re-registers under the same name
        unless you pass ``name``::

            diagnostics.check_egress(
                "management.azure.com",
                "api.fabric.microsoft.com",
                "fndry23541.services.ai.azure.com",
            )

        To keep the default hosts and just add one, set ``egress_hosts``::

            diagnostics.egress_hosts = (
                diagnostics.default_egress_hosts() + ["my.host.example"]
            )
        """

        def _probe() -> None:
            for fqdn in fqdns:
                self.probe_egress(fqdn, port=port, timeout=timeout, method=method)

        self.register_probe(name, _probe)

    # -- custom probes -----------------------------------------------------

    def register_probe(self, name: str, func: Callable[[], None]) -> None:
        """Add a probe to the cycle. Re-registering a name replaces it."""
        self._probes[name] = func

    def unregister_probe(self, name: str) -> None:
        self._probes.pop(name, None)

    def probe(self, name: str) -> Callable[[Callable[[], None]], Callable[[], None]]:
        """Decorator form of ``register_probe``."""

        def decorator(func: Callable[[], None]) -> Callable[[], None]:
            self.register_probe(name, func)
            return func

        return decorator

    # -- running -----------------------------------------------------------

    def run_once(self, cycle: int | None = None) -> None:
        """Run every registered probe once. Never raises.

        Each probe is isolated: one failing probe still lets the rest report,
        and a diagnostic must never take the agent down.
        """
        if not self.enabled:
            return
        label = "" if cycle is None else f" {cycle}"
        self.emit(f"--- probe cycle{label} ---")
        for name, func in list(self._probes.items()):
            try:
                func()
            except Exception as exc:
                self.emit(f"{name}: FAILED {type(exc).__name__}: {exc}")
        for key, value in self._context.items():
            self.emit(f"{key}: {value}")

    def start(self) -> None:
        """Start the repeating probe on a daemon thread. Idempotent.

        Call from a function the runtime actually executes - ``build_agent()``
        is a safe choice - not from ``main()``.
        """
        if not self.enabled:
            return
        with self._lock:
            if self._started:
                return
            self._started = True

        def _loop() -> None:
            cycle = 0
            while True:
                cycle += 1
                self.run_once(cycle)
                time.sleep(self.interval_seconds)

        threading.Thread(target=_loop, name="agent-diag-probe", daemon=True).start()
        self.emit(f"probe daemon started, interval={self.interval_seconds}s")

    # -- request-path hooks ------------------------------------------------

    def log_request(self, request: Any) -> None:
        """Log the caller's platform identity for one request.

        For protocols that hand the handler a Starlette request (Invocations).
        Reads ``request.state``, which the runtime populates from platform
        headers; ``getattr`` defaults keep this working locally where those
        headers are absent.
        """
        if not self.enabled:
            return
        state = getattr(request, "state", None)
        fields = ("invocation_id", "session_id", "user_id", "call_id")
        rendered = " ".join(f"{f}={getattr(state, f, None)}" for f in fields)
        self.emit(f"caller: {rendered}")

    def agent_middlewares(self) -> list[Any]:
        """Return middleware for ``Agent(middleware=...)``; ``[]`` when disabled.

        For protocols where the handler never sees the HTTP request (Responses),
        this is how to reach the caller's platform identity - the identity the
        On-Behalf-Of exchange is attempted for.
        """
        if not self.enabled:
            return []

        # Imported lazily so this module stays usable without agent_framework.
        from agent_framework import agent_middleware as _mark

        @_mark
        async def _log_caller(context: Any, call_next: Any) -> None:
            try:
                from azure.ai.agentserver.core import get_request_context

                ctx = get_request_context()
                caller = (
                    f"user_id={ctx.user_id} session_id={ctx.session_id} "
                    f"call_id={ctx.call_id}"
                )
            except Exception as exc:
                caller = f"<unavailable: {type(exc).__name__}>"
            self.emit(
                f"run: agent={context.agent.name} stream={context.stream} {caller}"
            )
            await call_next()

        return [_log_caller]

    def install_asgi(self, app: Any) -> None:
        """Log every HTTP request beneath the protocol layer. No-op when disabled.

        Catches requests that never reach the agent - 404s, health probes,
        protocol mismatches - which agent middleware by definition cannot see.
        This is how the Invocations route was confirmed to be ``/invocations``
        rather than ``/invoke``.

        Must be called while the app is still being built, i.e. at import time.
        Registering it inside ``main()`` is why an earlier revision never ran.
        """
        if not self.enabled:
            return
        app.add_middleware(DiagnosticsASGIMiddleware, diagnostics=self)


class DiagnosticsASGIMiddleware:
    """Pure-ASGI request logger. Prefer ``diagnostics.install_asgi(app)``.

    Safe to add directly to any ASGI app (Starlette, FastAPI, FastMCP's
    Streamable HTTP app). The enabled check lives here rather than only in
    ``install_asgi`` so a directly-wired middleware still honours it, and so
    toggling ``enabled`` at run time takes effect on an installed middleware.
    """

    def __init__(self, app: Any, diagnostics: Diagnostics | None = None) -> None:
        self.app = app
        self.diagnostics = diagnostics or globals()["diagnostics"]

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self.diagnostics.enabled and scope.get("type") == "http":
            self.diagnostics.emit(
                f"request: {scope.get('method')} {scope.get('path')}"
            )
        await self.app(scope, receive, send)


#: Module-level singleton. Import this rather than constructing your own.
diagnostics = Diagnostics()
