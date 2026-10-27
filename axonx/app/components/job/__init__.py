"""Job execution, response contracts and Step pipelines.

base: Execution contract shared by all Jobs.
command: Execute a service-owned CLI command with streaming output and cancellation cleanup.
pipeline: Ordered, streaming Step pipeline Job.
response: Job result folding and invocation-scoped response-completion callbacks.
"""
