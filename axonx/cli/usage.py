"""Usage text for the executable entry point."""

from ..config.defaults import AXONX_DEFAULT_CONNECT_HOST, AXONX_DEFAULT_PORT, AXONX_DEFAULT_REQUEST_TIMEOUT

CLI_USAGE = f"""Usage:
  axonx
  axonx help [--job NAME] [--target HOST:PORT]
  axonx diagnose [--target HOST:PORT]
  axonx JOB [--field value ...] [--client-timeout SECONDS] [--token TOKEN] [--stream true]
        [--stream-format blocks|json] [--target HOST:PORT]
  axonx wait_task --task-id ID --run-id ID [--client-timeout SECONDS]
  axonx exec [--task TASK] [--field value ...]
  axonx start [--config NAME_OR_PATH] [--cron NAME_OR_PATH]
  axonx plugin list|show|inspect|install|uninstall ... [--target HOST:PORT]
  axonx plugin build SOURCE [--output DIRECTORY] [--target HOST:PORT]
  axonx plugin install -e SOURCE

Service options: target={AXONX_DEFAULT_CONNECT_HOST}:{AXONX_DEFAULT_PORT}
client_timeout={AXONX_DEFAULT_REQUEST_TIMEOUT:g} token=null stream=false stream_format=blocks"""
