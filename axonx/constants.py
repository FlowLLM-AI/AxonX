"""Stable names and defaults shared across AxonX subsystems."""

AXONX_NAME = "AxonX"
AXONX_DEFAULT_TIMEZONE = "Asia/Shanghai"

# Every text file this project reads or writes is UTF-8 unless a caller names
# another codec, so the default is stated once.
AXONX_DEFAULT_ENCODING = "utf-8"

# Directory the logging subsystem and the application config both fall back to.
# They default to it independently, so the name is stated once.
AXONX_DEFAULT_LOG_DIR = "logs"

PLUGIN_ENTRY_POINT_GROUP = "axonx.plugins"

CONFIG_ENTRY_POINT_GROUP = "axonx.configs"

PLUGIN_MANIFEST = "plugin.yaml"

# Environment variable used by a running service to advertise its address to
# clients created in the same process.
AXONX_SERVICE_INFO = "AXONX_SERVICE_INFO"

# The JSON envelope ``AXONX_SERVICE_INFO`` carries. Its producer runs in the
# service process and its consumer in a client one, so both keys are named here.
SERVICE_INFO_HOST_KEY = "host"
SERVICE_INFO_PORT_KEY = "port"

# Internal handoff from an application task manager to its Task subprocess.
AXONX_TASK_WORKSPACE_DIR = "AXONX_TASK_WORKSPACE_DIR"
AXONX_TASK_LOG_DIR = "AXONX_TASK_LOG_DIR"
AXONX_TASK_TIMEZONE = "AXONX_TASK_TIMEZONE"
AXONX_TASK_ID = "AXONX_TASK_ID"
AXONX_TASK_RUN_ID = "AXONX_TASK_RUN_ID"
AXONX_TASK_CREATED_AT = "AXONX_TASK_CREATED_AT"

# Wildcard address used by servers to listen on every IPv4 interface.
AXONX_DEFAULT_BIND_HOST = "0.0.0.0"

# Loopback address used by clients when no remote service is configured.
AXONX_DEFAULT_CONNECT_HOST = "127.0.0.1"

AXONX_DEFAULT_PORT = 1024

# The built-in uvicorn service has no TLS configuration. Deployments that
# terminate TLS should pass their public HTTPS URL explicitly to the client.
AXONX_DEFAULT_SCHEME = "http"

AXONX_DEFAULT_REQUEST_TIMEOUT = 60.0

# The AxonX-over-HTTP wire protocol. A route, header or media type is spelled
# once here because each one has a producer and a consumer in different
# subsystems: a router answers what the client asks for, and the auth middleware
# guards the same paths the routers register.
PROTOCOL_ROUTE_FILES = "/files"
PROTOCOL_ROUTE_HEALTH = "/health"
PROTOCOL_ROUTE_JOBS = "/jobs"
PROTOCOL_ROUTE_MCP = "/mcp"
PROTOCOL_ROUTE_PROXY = "/proxy"

# Templated routes, so a router and its client cannot drift apart. Format the
# job name into these rather than rebuilding the path by hand.
PROTOCOL_ROUTE_JOB = "/jobs/{name}"
PROTOCOL_ROUTE_JOB_EVENTS = "/jobs/{name}/events"

# Route families the bearer token guards. ``/proxy`` is deliberately absent:
# proxy requests carry their own upstream credentials instead, and
# ``tests/test_http_proxy.py`` pins that a token-protected service still serves
# them without the service token.
PROTOCOL_AUTH_ROOTS = frozenset(
    {
        PROTOCOL_ROUTE_FILES,
        PROTOCOL_ROUTE_HEALTH,
        PROTOCOL_ROUTE_JOBS,
        PROTOCOL_ROUTE_MCP,
    },
)

PROTOCOL_AUTH_HEADER = "authorization"
PROTOCOL_AUTH_SCHEME = "Bearer"

# AxonX's own envelope around one copied file: the name to store it under and
# the workspace subdirectory to place it in.
PROTOCOL_FILE_NAME_HEADER = "x-file-name"
PROTOCOL_FILE_DIRECTORY_HEADER = "x-file-directory"

# Server-Sent Events framing, shared by the job stream route and its decoder.
PROTOCOL_SSE_MEDIA_TYPE = "text/event-stream"
PROTOCOL_SSE_EVENT_PREFIX = "event: "
PROTOCOL_SSE_DATA_PREFIX = "data: "

# Canonical Task identity. One module builds an ID and another parses it, so the
# separator, the optional timestamp format and the name pattern live here.
TASK_ID_SEPARATOR = "#"
TASK_ID_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S%f"
TASK_NAME_PATTERN = r"^[A-Za-z0-9-]{1,32}$"

# The largest file one upload request may stage, and the largest archive the sync
# component may build to send through one. An archive is uploaded as a single
# request, so the sync budget has to stay below the receiving workspace's upload
# limit; keeping both here is what makes that relation visible.
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024

# Request budget shared by the Tushare connector and the Task built on it.
TUSHARE_TIMEOUT_SECONDS = 600

LOG_ARGUMENT_MAX_LENGTH = 1000

# Public command-line interface. Keeping command metadata here gives parsing
# and dispatch one shared vocabulary.
CLI_EXEC_COMMAND = "exec"
CLI_HELP_COMMAND = "help"
CLI_PLUGIN_COMMAND = "plugin"
CLI_START_COMMAND = "start"

CLI_CLIENT_OPTIONS = frozenset(
    {"host_ip", "host_port", "timeout", "token", "stream", "stream_format"},
)

# Internal Job argument carrying the original tokens after the command name.
CLI_RAW_ARGUMENTS = "_axonx_argv"

# Reserved Job argument used by Application to select a configured remote node.
REMOTE_IP_ARGUMENT = "remote_ip"

# Reserved Job argument counting how deep a job sits in an agent's call chain.
# Jobs that declare it may be invoked by an agent, and the agent increments it
# on every tool call so a self-call cannot recurse without bound.
AGENT_DEPTH_ARGUMENT = "agent_depth"

CLI_LOCAL_COMMANDS = frozenset(
    {CLI_EXEC_COMMAND, CLI_HELP_COMMAND, CLI_PLUGIN_COMMAND, CLI_START_COMMAND},
)

CLI_PASSTHROUGH_COMMANDS = frozenset({CLI_PLUGIN_COMMAND})

CLI_USAGE = f"""Usage:
  axonx [--host-ip IP] [--host-port PORT] [--timeout SECONDS] [--token TOKEN]
        [--stream true] [--stream-format blocks|json] COMMAND ...
  axonx exec [--task TASK] [--field value ...]
  axonx submit --task TASK [--field value ...]
  axonx start [--config app.yaml]
  axonx plugin list|show|inspect|build|install|uninstall ...
  axonx JOB [--field value ...]

Remote Job options: host_ip={AXONX_DEFAULT_CONNECT_HOST} host_port={AXONX_DEFAULT_PORT}
timeout={AXONX_DEFAULT_REQUEST_TIMEOUT:g} token=null stream=false stream_format=blocks"""
