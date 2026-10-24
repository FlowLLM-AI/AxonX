# Jobs and Tasks

A Job is a request processed by the service. Task observation Jobs return snapshots, logs or event streams. A Task is a synchronous research execution started through `axonx exec`, with its own persisted identity and artifacts.

The Task Runner owns lifecycle publication and cleanup. The service's TaskRepository polls metadata written by execution processes and builds status summaries and dependency graphs. There is no service-side TaskManager or background submission handle.

`exec` prints Task output and returns its exit code; ordinary Jobs use JobResponse. `wait_task` and `stream_task` observe an existing execution. Studio displays Task definitions and existing records without Task launch, cancel or delete controls.

The remote CLI, generic workspace deletion and replica synchronization remain separate capabilities. Remote exec is still synchronous and its process is owned by the remote CLI request; closing that request or stopping its service terminates that command. This differs from independently launched local exec.
