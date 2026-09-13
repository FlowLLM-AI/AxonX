"""Stable names and defaults shared across AxonX subsystems."""

AXONX_NAME = "AxonX"

PLUGIN_ENTRY_POINT_GROUP = "axonx.plugins"

CONFIG_ENTRY_POINT_GROUP = "axonx.configs"

PLUGIN_MANIFEST = "plugin.yaml"

# Environment variable used by a running service to advertise its address to
# clients created in the same process.
AXONX_SERVICE_INFO = "AXONX_SERVICE_INFO"

# Internal handoff from an application task manager to its Task subprocess.
AXONX_TASK_WORKSPACE_DIR = "AXONX_TASK_WORKSPACE_DIR"
AXONX_TASK_LOG_DIR = "AXONX_TASK_LOG_DIR"

# Wildcard address used by servers to listen on every IPv4 interface.
AXONX_DEFAULT_BIND_HOST = "0.0.0.0"

# Loopback address used by clients when no remote service is configured.
AXONX_DEFAULT_CONNECT_HOST = "127.0.0.1"

AXONX_DEFAULT_PORT = 1024

# The built-in uvicorn service has no TLS configuration. Deployments that
# terminate TLS should pass their public HTTPS URL explicitly to the client.
AXONX_DEFAULT_SCHEME = "http"

AXONX_DEFAULT_REQUEST_TIMEOUT = 60.0

LOG_ARGUMENT_MAX_LENGTH = 1000

# Public command-line interface. Keeping command metadata here gives parsing
# and dispatch one shared vocabulary.
CLI_CLIENT_OPTIONS = frozenset({"host_ip", "host_port", "timeout"})

# Internal Job argument carrying the original tokens after the command name.
CLI_RAW_ARGUMENTS = "_axonx_argv"

# Reserved Job argument used by Application to select a configured remote node.
REMOTE_IP_ARGUMENT = "remote_ip"

CLI_LOCAL_COMMANDS = frozenset({"exec", "help", "plugin", "start"})

CLI_PASSTHROUGH_COMMANDS = frozenset({"plugin"})

CLI_USAGE = f"""Usage:
  axonx [--host-ip IP] [--host-port PORT] [--timeout SECONDS] COMMAND ...
  axonx exec [--task TASK] [--field value ...]
  axonx submit --task TASK [--field value ...]
  axonx start [--config app.yaml]
  axonx plugin COMMAND ...
  axonx JOB [--field value ...]

Remote Job options: host_ip={AXONX_DEFAULT_CONNECT_HOST} host_port={AXONX_DEFAULT_PORT}
timeout={AXONX_DEFAULT_REQUEST_TIMEOUT:g}"""
