import asyncio
import atexit
import hashlib
import os
import platform
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, local

from cffi import FFI

_SOURCE = Path(__file__).with_name("http.c")
_CDEF = """
typedef struct AxisHttpClient AxisHttpClient;
typedef struct {
    long status;
    char *body;
    size_t body_length;
    char *link_header;
    char *error;
} AxisHttpResponse;
AxisHttpClient *axis_http_client_new(void);
void axis_http_client_free(AxisHttpClient *);
int axis_http_request(AxisHttpClient *, const char *, const char *, const char *,
                      const char *, long, AxisHttpResponse *);
int axis_http_init(void);
void axis_http_response_free(AxisHttpResponse *);
"""
_ffi = FFI()
_ffi.cdef(_CDEF)


class APITransportError(Exception):
    pass


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes
    link_header: str | None


def _library_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        suffix = ".dylib"
        link_flags = ["-dynamiclib", "-fPIC"]
    elif system == "Linux":
        suffix = ".so"
        link_flags = ["-shared", "-fPIC"]
    else:
        raise APITransportError(f"Native API transport is unsupported on {system}.")

    source = _SOURCE.read_bytes()
    digest = hashlib.sha256(
        source + system.encode() + platform.machine().encode()
    ).hexdigest()[:20]
    cache_dir = Path.home() / ".cache" / "axis" / "native" / digest
    library = cache_dir / f"libaxis_http{suffix}"
    if library.is_file():
        return library

    try:
        pkg_config = subprocess.run(
            ["pkg-config", "--cflags", "--libs", "libcurl"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise APITransportError(
            "Native API library is not built and libcurl build flags could not "
            "be discovered. Run `nix develop` once to build it, or install "
            "libcurl development files and pkg-config."
        ) from error

    flags = shlex.split(pkg_config.stdout)
    compiler = shlex.split(os.environ.get("CC", "cc"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="libaxis_http-",
        suffix=suffix,
        dir=cache_dir,
    )
    os.close(descriptor)
    temporary_library = Path(temporary_name)
    try:
        subprocess.run(
            [
                *compiler,
                *link_flags,
                str(_SOURCE),
                "-o",
                str(temporary_library),
                *flags,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        os.replace(temporary_library, library)
    except (OSError, subprocess.CalledProcessError) as error:
        temporary_library.unlink(missing_ok=True)
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        raise APITransportError(
            f"Could not compile the native API library: {detail}"
        ) from error

    return library


def _load_library():
    try:
        library = _ffi.dlopen(str(_library_path()))
    except OSError as error:
        raise APITransportError(
            f"Could not load the native API library: {error}"
        ) from error
    if library.axis_http_init() != 0:
        raise APITransportError("Could not initialize the native HTTP client.")
    return library


_library = None
_library_lock = Lock()
_thread_clients = local()
_created_clients: list[object] = []
_client_lock = Lock()


def _close_clients() -> None:
    if _library is None:
        return
    with _client_lock:
        for client in _created_clients:
            _library.axis_http_client_free(client)
        _created_clients.clear()


atexit.register(_close_clients)


def _client():
    client = getattr(_thread_clients, "client", None)
    if client is None:
        client = _library.axis_http_client_new()
        if client == _ffi.NULL:
            raise APITransportError("Could not create a native HTTP client.")
        _thread_clients.client = client
        with _client_lock:
            _created_clients.append(client)
    return client


def _request_sync(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
    timeout: float,
) -> HTTPResponse:
    global _library
    if _library is None:
        with _library_lock:
            if _library is None:
                _library = _load_library()

    for name, value in headers.items():
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise ValueError("HTTP headers cannot contain newline characters.")
    header_bytes = "\n".join(
        f"{name}: {value}" for name, value in headers.items()
    ).encode()
    response = _ffi.new("AxisHttpResponse *")
    result = _library.axis_http_request(
        _client(),
        method.encode(),
        url.encode(),
        _ffi.NULL if body is None else body.encode(),
        header_bytes,
        int(timeout * 1000),
        response,
    )
    try:
        if result != 0:
            message = (
                _ffi.string(response.error).decode(errors="replace")
                if response.error != _ffi.NULL
                else "Unknown libcurl error."
            )
            raise APITransportError(message)
        response_body = (
            bytes(_ffi.buffer(response.body, response.body_length))
            if response.body != _ffi.NULL
            else b""
        )
        link_header = (
            _ffi.string(response.link_header).decode("latin-1")
            if response.link_header != _ffi.NULL
            else None
        )
        return HTTPResponse(int(response.status), response_body, link_header)
    finally:
        _library.axis_http_response_free(response)


async def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout: float = 15,
) -> HTTPResponse:
    return await asyncio.to_thread(
        _request_sync,
        method,
        url,
        headers or {},
        body,
        timeout,
    )
