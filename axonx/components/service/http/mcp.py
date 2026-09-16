"""MCP registration for public Jobs."""

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from ....schema import Response


def create_mcp_server(app, public_jobs) -> FastMCP:
    """Register the same public Jobs exposed over HTTP."""
    server = FastMCP(name=app.app_config.app_name)
    for job in public_jobs.values():

        def make_tool(job_name):
            async def execute_tool(**arguments) -> Response:
                return await app.run_job(job_name, **arguments)

            return execute_tool

        server.add_tool(
            FunctionTool(
                name=job.name,
                description=job.description,
                parameters=job.parameters,
                output_schema=Response.model_json_schema(),
                fn=make_tool(job.name),
                return_type=Response,
            ),
        )
    return server
