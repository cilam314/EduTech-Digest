# 阅读清单、归档与定时运行

日常阅读只需打开 reports/latest.md。

- 历次有效条目按原文链接合并去重，同一链接只保留更新后的条目。
- 当前日期范围展示最近25条，往期条目折叠；全部条目保存在archive/entries.json。
- 历史dated报告移入archive/reports，原文逐字节核对后才从reports移走，保留核查依据。
- 新运行没有新条目时，不会清空已有清单。
- 旧版来源误归类不会在迁移时被自动纠正为已核实来源；旧条目保守标记为历史导入待复核。
- 搜索记录放在清单底部的折叠区域，详细诊断更新到state/latest_status.json。
- state/seen_articles.json继续保留，防止重复总结。不要删除state文件夹。

Actions里的每一条记录是一次执行历史，不是多份定时任务，不需要为了避免重复执行而删除。
EduTech Digest是正式定时工作流；Spark Search Diagnose仅在手动点击时运行。

当前定时是每周一、三、五、日北京时间09:00，采用GitHub的UTC表达式0 1 * * 0,1,3,5。
它是每周固定四天，不是严格每48小时。工作流在默认分支main且Actions启用时由GitHub自动触发，电脑无需开机，也无需每次手动点运行。
GitHub调度可能延迟。手动Run workflow用于临时更新/测试，重跑旧任务会使用旧提交和旧参数。

本次清理保留所有运行历史和旧报告归档。以后如需删除archive里的历史文件，可在核对最新清单和备份后再单独清理。

官方定时说明：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
