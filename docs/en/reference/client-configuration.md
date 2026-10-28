# Client Configuration

Connection configuration is separate from application and execution configuration.

## ConnectionOptions

`axonx.client.config.ConnectionOptions` validates target (optional), timeout (positive float, default 60 seconds) and optional nonempty token. Instances are frozen and reject extra fields. CLI ClientOptions adds stream and stream_format (`blocks` or `json`).

## Address rules

Targets are HOST:PORT or HTTP(S) URLs with an explicit port. A trailing root slash is normalized away; subpaths, query/fragment, credentials and invalid ports are rejected. Pass the service base URL, not `/mcp` or a Job route. Python clients use AXONX_SERVICE_TARGET when target is omitted, then http://127.0.0.1:1024.

## CLI token sources

An explicit --token wins. Otherwise local CLI uses AXONX_SERVICE_TOKEN; explicit --target uses AXONX_TARGET_TOKEN. CLI loads .env without replacing existing environment variables. These fields are client options, never public Job arguments.

## Explicit Python connections

```python
from axonx.client.http import HttpClient
client = HttpClient(target="http://node-b:1024", token="replace-token", timeout=600.0)
```

Start/close the client with async with. Python HTTP/MCP clients receive token explicitly and do not discover CLI token variables automatically.

## Studio same-origin forwarding

Studio uses its local service and can request a configured remote target. Backend forwarding resolves address/token from ApplicationConfig.targets; a client cannot supply an arbitrary remote credential in business arguments. Explicit CLI target connections go directly to that target.

## Command handoff

The daemon/service supplies AXONX_SERVICE_TARGET so native CLI children can query execution defaults. The internal AXONX_CLI_REQUEST_ID associates response-boundary callbacks and prevents nested forwarding/service startup. Execution identity lives in Task metadata, not a collection of Task environment variables. Do not fabricate internal handoff fields.

## Handling connection failures

Only a connection failure lets local exec/kill fall back to built-in execution defaults. Authentication, protocol or failed get_config responses propagate. An observation timeout does not prove Task failure. A native command cancellation may terminate the owned remote process group; inspect current metadata before retrying.
