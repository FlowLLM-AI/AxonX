"""Stable constants owned by this subsystem."""

AXONX_SERVICE_TARGET = "AXONX_SERVICE_TARGET"

PROTOCOL_ROUTE_UPLOAD = "/upload"

PROTOCOL_CLI_REQUEST_HEADER = "X-AxonX-Cli-Request"


PROTOCOL_ROUTE_HEALTH = "/health"

PROTOCOL_ROUTE_JOBS = "/jobs"

PROTOCOL_ROUTE_MCP = "/mcp"

PROTOCOL_ROUTE_PROXY = "/proxy"

PROTOCOL_ROUTE_JOB = "/jobs/{name}"

PROTOCOL_ROUTE_JOB_EVENTS = "/jobs/{name}/events"

PROTOCOL_AUTH_ROOTS = frozenset(
    {
        PROTOCOL_ROUTE_UPLOAD,
        PROTOCOL_ROUTE_HEALTH,
        PROTOCOL_ROUTE_JOBS,
        PROTOCOL_ROUTE_MCP,
    },
)

PROTOCOL_AUTH_HEADER = "authorization"

PROTOCOL_AUTH_SCHEME = "Bearer"

PROTOCOL_FILE_NAME_HEADER = "x-file-name"

PROTOCOL_FILE_DIRECTORY_HEADER = "x-file-directory"

PROTOCOL_SSE_MEDIA_TYPE = "text/event-stream"

PROTOCOL_SSE_EVENT_PREFIX = "event: "

PROTOCOL_SSE_DATA_PREFIX = "data: "

TARGET_ARGUMENT = "target"

AGENT_DEPTH_ARGUMENT = "agent_depth"
