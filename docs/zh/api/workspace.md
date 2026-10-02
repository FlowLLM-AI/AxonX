# 工作区与文件传输 API

工作区 Job 用于目录、元数据与数据预览；文件传输是独立 HTTP 路由，用于暂存 wheel 与同步归档。

![工作区与文件传输 API调用示意](../../figures/api/upload.svg)

## 调用约定

以下均为 `POST /jobs/{name}`，请求体是 `{"arguments":{...}}`。远程转发时在封装顶层添加 `target`，不能放进 arguments。每个响应使用 [JobResponse](overview.md#响应与错误)，表格默认值依据当前内置配置和 Step。部署可修改 Job Schema，运行服务的 `/jobs` 是最终依据。

所有示例 JSON 均为结构示例；任务、会话、文件路径与哈希必须替换为本服务实际返回的值。完整通用 TaskStatus 字段见 [Task 协议](../reference/task-contracts.md)。

## 接口清单

| Job              | 用途                              |
| ---------------- | --------------------------------- |
| `list_entries`   | 列出工作区内一层目录。            |
| `list_task_runs` | 列出含 metadata.json 的任务目录。 |
| `preview_file`   | 预览支持类型的文件。              |
| `delete_entries` | 删除工作区中的文件或目录。        |

## list_entries

列出工作区内一层目录。

| 参数   | 类型   | 必填 | 默认值 | 约束与含义         |
| ------ | ------ | ---- | ------ | ------------------ |
| `path` | string | 否   | `""`   | 服务工作区相对路径 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

answer 为 WorkspaceListing：path、entries、truncated。每个 entry 含 name、path、kind、preview_kind、supported、size、modified_at。

```json
{
  "answer": {
    "path": "",
    "entries": [],
    "truncated": false
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

path 默认空字符串表示根目录；目录优先排序。最多返回 5000 项，truncated=true 表示列表截断，不提供 offset 分页。

## list_task_runs

列出含 metadata.json 的任务目录。

| 参数        | 类型   | 必填 | 默认值      | 约束与含义                                                    |
| ----------- | ------ | ---- | ----------- | ------------------------------------------------------------- |
| `task_type` | string | 是   | `—（省略）` | 任务类型目录；minLength=1, 正则 `^[A-Za-z0-9][A-Za-z0-9_-]*$` |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "task_type": "train"
  }
}
```

**响应**

answer 与 WorkspaceListing 相同，只保留任务结果目录。

```json
{
  "answer": {
    "path": "train",
    "entries": [],
    "truncated": false
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

正在执行或失败而没有 metadata 的目录不进入研究结果列表。task_type 是目录名，不是 Task 注册名。

## preview_file

预览支持类型的文件。

| 参数     | 类型    | 必填 | 默认值      | 约束与含义                                                  |
| -------- | ------- | ---- | ----------- | ----------------------------------------------------------- |
| `path`   | string  | 是   | `—（省略）` | 服务工作区相对路径                                          |
| `offset` | integer | 否   | `0`         | CSV/Parquet 预览跳过的数据行数；minimum=0                   |
| `limit`  | integer | 否   | `200`       | CSV/Parquet 预览最多返回的数据行数；minimum=1, maximum=5000 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "path": "base/base#demo#api-demo/metadata.json"
  }
}
```

**响应**

answer 按 kind 判别：text/markdown/json/yaml/csv/parquet/unsupported；每种都有 size。

```json
{
  "answer": {
    "kind": "json",
    "size": 1200,
    "content": "",
    "data": {},
    "parse_error": null,
    "truncated": false
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

offset/limit 仅对 CSV、Parquet 的数据行有效，默认 0/200，上限 5000。text/markdown 最多读取 512 KiB；JSON/YAML 超过 32 MiB 返回 parse_error。解析失败可仍是 success=true，必须查看 parse_error。

## delete_entries

删除工作区中的文件或目录。

| 参数    | 类型  | 必填 | 默认值      | 约束与含义                                           |
| ------- | ----- | ---- | ----------- | ---------------------------------------------------- |
| `paths` | array | 是   | `—（省略）` | 待删除的工作区相对路径列表；maxItems=200, minItems=1 |

只接受表中业务字段。

**请求**

```json
{
  "arguments": {
    "paths": ["tmp/example.txt"]
  }
}
```

**响应**

answer 是 DeletedEntry 数组，每项 deleted 为相对路径，kind 为 file/directory。

```json
{
  "answer": [
    {
      "deleted": "tmp/example.txt",
      "kind": "file"
    }
  ],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

最多 200 路径；根目录与逃逸路径不可删除。任务目录应优先使用 delete_tasks，保留任务状态和日志管理约束。

## 相关文档

- [协议、鉴权与错误](overview.md)
- [工作区操作](../guides/workspace-files.md)
- [CLI 参考](../reference/cli.md)
- [事件协议](events.md)

实现依据：`axonx/config/default.yaml`、`axonx/steps/workspace/` 与 `axonx/components/service/http/jobs.py`。

## 文件上传与清理

上传以原始二进制请求体发送，不是 multipart/form-data。`x-file-name` 为必填文件名 header；`x-file-directory` 可选，指定以 tmp 开头的工作区相对子目录，不能指定工作区任意位置。

```bash
curl -s -X POST http://127.0.0.1:1024/files \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN" \
  -H 'Content-Type: application/octet-stream' \
  -H 'x-file-name: axonx_example-0.1.0-py3-none-any.whl' \
  -H 'x-file-directory: tmp/plugins' \
  --data-binary @dist/axonx_example-0.1.0-py3-none-any.whl
```

FileCopy 的响应形状如下，哈希和字节大小必须以真实返回为准：

```json
{
  "answer": {
    "path": "tmp/plugins/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/axonx_example-0.1.0-py3-none-any.whl",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "size": 4096
  },
  "success": true,
  "metadata": {}
}
```

文件暂存目录按内容 SHA-256 命名，相同内容与文件名上传是幂等的。默认单文件上限为 256 MiB；服务同时检查 Content-Length 和实际流入字节数。非法 Content-Length 为 400，超限为 413；缺失/非法文件名、目录逃逸等为 422，符号链接或不同内容占据目的位置为 409。

消费者 install_plugin、sync_tasks 使用返回的 path。安装还要传 sha256。上传完成不代表插件已安装，也不代表任务快照已应用。消费者会清理暂存制品；未消费时可主动清理：

```bash
curl -s -X DELETE 'http://127.0.0.1:1024/files?path=tmp%2Fplugins%2Fyour-digest%2Fyour-wheel.whl' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
```

上例路径为占位，需替换实际 path；cleanup 响应 answer 为 `{"path":"返回的路径"}`。重复清理已消费的合法路径是无害的；此路由只清理暂存文件，不能删除任意工作区文件。后端路径规则拒绝绝对路径、逃逸路径和 tmp 外的路径。

## 预览响应分型

| kind        | 特有字段                                                     | 消费建议                             |
| ----------- | ------------------------------------------------------------ | ------------------------------------ |
| text        | content、truncated                                           | 内容截断时不要推断完整文件           |
| markdown    | content、frontmatter、frontmatter_error、truncated           | frontmatter 单独读取，错误单独提示   |
| json / yaml | content、data、parse_error、truncated                        | parse_error 非空时不能使用 data 分析 |
| csv         | columns、rows、offset、limit、has_more                       | 下一页 offset 加已返回行数           |
| parquet     | CSV 同类字段，以及 column_schema、row_count、row_group_count | schema 提供列类型与 nullable         |
| unsupported | size                                                         | 接口不提供该格式的预览内容           |

原始文件字节大小、行分页 offset 与日志字节 offset 是三种不同信息。文本预览没有通用字符分页。Parquet 行数与分组信息来自文件元数据，返回 rows 只是当前窗口。
