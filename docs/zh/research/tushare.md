---
title: Tushare 数据下载
description: 下载原始行情分区、静态主数据和沪深 300 权重。
---

# Tushare 数据下载

内置 `download_tushare_task` 是 `api` 类型 Task，将请求结果整理为工作区内的 Parquet 文件。它负责原始数据准备，Alpha158 特征生成由 ETL 插件完成。

![下载与存储](../../figures/research/tushare-layout.svg)

## 配置数据连接

在执行 Task 的服务环境中设置：

```bash
export AXONX_TUSHARE_TOKEN='<数据接口 token>'
# 使用自有兼容接口或代理时才覆盖地址
export AXONX_TUSHARE_BASE_URL='http://<数据服务>/dataapi'
```

内置客户端默认地址是 `http://api.waditu.com/dataapi`，请求使用 `<base_url>/<api_name>`，以 JSON 提交 `api_name`、`token`、`params` 和 `fields`。自有服务需兼容该协议。这个 token 与保护 AxonX HTTP 服务的 `AXONX_SERVICE_TOKEN` 是两种凭据。

数据服务可访问范围、额度与授权由上游决定；本文仅说明当前客户端和任务的行为。通过 AxonX 代理时参阅[HTTP 代理](../guides/http-proxy.md)，不要仅替换地址就假定上游协议一致。

## 参数与日期

![Tushare download submission form](../../figures/studio/tushare-submit.png)

在 **Submit task** 选择 `download_tushare_task`，表单根据任务 Schema 展示日期、自然日回溯、请求超时与数据组。图中为未提交的默认配置；填写前先确认执行机器的数据凭据。

| 字段 | 默认值 | 用途 |
| --- | --- | --- |
| `start_date` | 空 | 开始日期，包含当天 |
| `end_date` | 空 | 结束日期，空时为本地当天；未来日期截断到当天 |
| `days_back` | `7` | 未给开始日期时，向前覆盖的自然日数 |
| `timeout` | `600` 秒 | 每次网络请求的超时秒数，必须大于零 |
| `datasets` | 全部五组 | 逗号分隔字符串，也接受 JSON 字符串列表 |

日期接受 `YYYYMMDD` 和 ISO 日期；CLI 的八位整数日期会转换回字符串。日期范围按自然日枚举，节假日接口返回空数据时不会写文件。`days_back` 是自然日数，不是交易日数。

```bash
axonx submit --task download_tushare_task --days-back 7
axonx submit --task download_tushare_task \
  --start-date 20230101 --end-date 20231231 \
  --datasets 'static,stk_limit,daily,adj_factor,index_weight'
```

提交后保留 TaskHandle，调用 `wait_task` 确认执行完成。长区间可能包含大量请求，客户端等待超时与单次接口 timeout 应分别设置，见[研究流程](workflow.md)。

## 数据组

| 可选组 | 查询内容 | 写入位置 |
| --- | --- | --- |
| `static` | `stock_basic`、`namechange`、`trade_cal` | `tushare/` 根目录 |
| `stk_limit` | 官方涨跌停价格 | 对应日期分区 |
| `daily` | 未复权日线行情 | 对应日期分区 |
| `adj_factor` | 复权因子 | 对应日期分区 |
| `index_weight` | 沪深 300 成分权重，`000300.SH` | 权重记录日期分区 |

`static` 会查询股票的 L、D、P、G 状态并合并去重。静态文件是查询时得到的快照，不能把 `stock_basic` 快照本身当成完整历史成分数据。历史名称变化单独来自 `namechange`。

权重查询按覆盖的月份调用接口；月份边界可超出请求的起止日。结果按返回的权重日期分区，不为每个交易日复制一份权重。

仅更新行情可使用：

```bash
axonx submit --task download_tushare_task \
  --start-date 20240101 --end-date 20240131 \
  --datasets 'daily,adj_factor'
```

数据组之间可以独立选择，但 a158 ETL 至少需要行情、复权、交易日历、股票主数据和历史名称；官方涨跌停数据以及指数权重影响可交易性和基准解释。

## 输出目录

![Tushare calendar Parquet preview](../../figures/studio/tushare-preview.png)

在 Studio 的 **Tushare data** 页面选择静态文件或日期分区，右侧展示 Parquet Schema 与分页数据。图中为远程工作区已有的交易日历文件；预览不代表已加载全量表。

以下以默认工作区 `.axonx/` 为例：

```text
.axonx/
  tushare/
    stock_basic.parquet
    namechange.parquet
    trade_cal.parquet
    2023/
      20230103/
        daily.parquet
        adj_factor.parquet
        stk_limit.parquet
      20230131/
        index_weight.parquet
```

非空响应先检查声明字段，稳定排序后原子写入 Parquet，使用 zstd 压缩。相同文件路径再次下载会替换已有文件；空响应跳过写入，不会主动删除已存在的旧文件。

下载任务 metadata 的 `output_params` 包含 `start_date`、`end_date`、`files` 和按数据集统计的 `rows`。`files` 是实际写入文件的字符串路径清单，不是标准研究任务的目录内 `artifacts` 映射。

## 完整性与失败

客户端对网络错误及指定暂态错误做有限重试；频率限制有独立预算，日志会显示等待时间和重试次数。收到非法 JSON、非法表结构或未声明支持的错误会失败。

静态查询使用分页接口，分页结果去重，并检测重复页和最大页数。日频与权重查询要求单次结果完整；若返回 `has_more=true` 会报错，避免把截断数据当完整分区。

| 现象 | 检查与处理 |
| --- | --- |
| 上游错误或授权失败 | token、兼容地址和数据服务权限 |
| 重试等待很久 | 任务日志中的限频原因与重试预算 |
| metadata 中某数据集行数为零 | 是否选择该组，日期是否开市，上游是否返回空集 |
| ETL 缺少主数据 | 单独下载 `static` 并检查三个静态文件 |
| ETL 历史覆盖不足 | 下载更早历史；最近 7 天不足以支持多年训练 |

原始数据位于任务目录之外，任务快照同步不会自动复制 `tushare/`。迁移研究环境时独立备份数据根目录，或者先将研究所需数据生成并保存到 ETL 任务产物中。

## 相关文档与实现

- [工作区浏览](../guides/workspace-files.md)、[量化研究流程](workflow.md)
- [`下载 Task`](../../../axonx/task/builtins/tushare/task.py)
- [`客户端与重试`](../../../axonx/task/builtins/tushare/client.py)
