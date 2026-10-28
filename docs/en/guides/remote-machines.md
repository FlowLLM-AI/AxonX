# Remote Machines

## Prepare the target service

Run `axonx app --service.host 0.0.0.0 --service.port 1024` on the destination with AXONX_SERVICE_TOKEN configured. Ensure network access and the intended interpreter, workspace, plugin dependencies and input files. Explicit CLI targets connect directly; they require a service with authenticated cli capability for native commands.

## CLI direct connections

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx plugin list --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

Ordinary Jobs call the target directly. Native commands forward argv through cli. Exec waits and streams target stdout/stderr, preserving the target exit code. Retain target, Task ID and started_at for follow-up observations. Connection cancellation may stop the owned remote execution; inspect before retrying.

## Studio backend forwarding

Configure target address/token in the local service's targets list. Studio selects that machine and sends a transport-level target; the backend resolves its credential. Job arguments do not override routing credentials. Each target has independent state and Agent sessions.

## Remote files and plugins

All native command paths are interpreted at the target service workspace, including plugin install/build/inspect source paths. --target does not upload local files. Build a local wheel, upload to /upload, install the returned absolute location, clean relative path and restart the persistent service to refresh its Task catalog. See [Plugin deployment](../plugins/management.md).

## Connectivity, resources and termination

Use list_machines/machine_status/diagnose for observed resources; there is no automatic machine scheduling. For kill use the source execution_target and workspace_dir from metadata. A display replica cannot control the source process, and machine_id is not an address.

[Authentication](authentication.md) · [Deployment](deployment.md) · [Task management](task-management.md)
