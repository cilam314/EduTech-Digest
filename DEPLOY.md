# 教育技术简报 · 云端部署说明

## 2026-11-03 账号校准版

已根据用户提供的两篇原文核实“教育技术学”和“教育数字化100人”的页面账号、公开微信号及biz标识。
本次更新三个必需文件：scripts/run_digest.py、scripts/account_profiles.json、tests/test_digest.py。
工作流无需再次调整，保留每周一三五日北京时间09:00。

- 配置中的账号按biz标识校验来源，名称相同但biz不同的候选会在模型调用之前剔除。
- 每个已配置账号执行名称检索与公开微信号检索，合并去重候选；样例链接也作为已知入口。
- 样例入口用于验证获取/匹配，不代表自动发现了该账号后续的所有新文章。
- “教育技术学”的样例发布时间2026-11-03 10:00；“教育数字化100人”的样例为2026-09-21 11:50，后者超出11月3日本期，不会当作新消息。
- 日期已知且超出本期的非期刊条目提前剔除，减少不必要的DeepSeek调用。
- 其余23个账号尚未配置biz，仍使用前一版的保守来源归类。
- 不清除state，不改写历史报告。模型/搜索仍需云端真实运行验证，不保证搜索收录完整。

## 2026-11-03 修正：来源归属与503重试

如已部署第一版，来源修正需要覆盖 scripts/run_digest.py、tests/test_digest.py，再手动运行3个账号。
本包另将工作流改为每周一、三、五、日北京时间09:00；需要同步替换 .github/workflows/digest.yml。
不需要修改Secrets、prompt.md、read_article.py，也不要删除state或历史简报。
历史报告不会被改写；新报告会将已确认账号来源、期刊目录线索、相关领域动态分开。
首次修正版重跑时已收录链接仍会被去重，因此可能没有重复条目。

- 引用标签显示实际域名/微信账号，检索使用的目标账号名单独列出，避免误认为原文发布者。
- 微信身份使用页面js_name账号标签，不能仅凭文章作者署名确认账号归属。
- 非期刊优先限定mp.weixin.qq.com搜索，无结果才执行一次全网补充。此时最多会使用两次搜索调用/账号。
- 旧或日期未知的普通新闻不能借A类绕过日期筛选；仅标题明确含目标期刊名与期号/目录的线索可单列为期刊目录线索，归属仍需核实。
- HTTP429/5xx最多尝试4次，等待5、10、20秒；Retry-After以30秒为上限。503说明服务端暂不可用，不能据此判断密钥/余额错误。
- 趋势的跨来源检查依据实际来源标签，不再把不同检索账号当作不同内容来源。

运行方式：GitHub Actions → Tavily搜索 → 微信正文脚本/Tavily正文 → DeepSeek分析 → Markdown简报。
无需本地电脑开机，不安装Codex，不使用本地Codex的登录或额度。

## 上传文件

先解压部署包，找到含有 prompt.md、scripts、tests、.github 的这一层。
你现有的 prompt.md 和 scripts/read_article.py 可以保持原样；包中这两个文件来自你提供的本地文件。

在GitHub仓库根目录（不是scripts目录）通过 Add file → Upload files 上传：

- scripts/run_digest.py（将整个scripts文件夹拖入根目录可保留路径）
- tests 文件夹
- DEPLOY.md（本说明，可选）

然后在仓库根目录 Add file → Create new file，文件名完整填写：

`.github/workflows/digest.yml`

用文本编辑器打开部署包的同名文件，将全部内容复制到GitHub编辑框，点击 Commit changes，提交到main。
这样无需依赖浏览器是否正确上传以点开头的 .github 文件夹。
不要将整个 edutech-cloud 文件夹作为仓库的下一层，否则工作流找不到路径。

最终必须是：

```text
仓库根目录/
├── prompt.md
├── DEPLOY.md
├── scripts/
│   ├── read_article.py
│   ├── account_profiles.json
│   └── run_digest.py
├── tests/
│   └── test_digest.py
└── .github/
    └── workflows/
        └── digest.yml
```

reports 和 state 会在成功运行时自动创建，不需要事先创建空文件夹。
README.md可以保留你仓库已有版本。程序只使用Python标准库，无需requirements.txt。

## 密钥与模型

Settings → Secrets and variables → Actions → Secrets 中已有：

- TAVILY_API_KEY
- DEEPSEEK_API_KEY

不要上传 .env、API密钥、本地auth.json、浏览器Cookie或整个.codex目录。
默认模型是DeepSeek官方文档目前列出的 deepseek-flash；以后如需更换，可在同一页面的 Variables 标签增加
DEEPSEEK_MODEL，填写账号实际支持的模型名称。不填写则使用默认模型。

API调用使用服务商的API额度/余额，不能用“密钥已配置”判断余额是否充足。

## 试运行

打开 Actions → EduTech Digest → Run workflow：

1. 选择main分支。
2. account_limit首次选3（测试一个期刊、一个机构、一个行业公众号）。
3. 点击Run workflow，等待执行结束。
4. 查看运行日志：测试、生成、保存、备份、服务状态检查。
5. 回到Code，查看reports里的中文简报，以及latest_status.json。
6. 试运行正常后手动再运行一次，选择25。

运行时间受搜索和模型速度影响。搜索无命中可能产生0条结果；这是有效空结果，不等于采集完整。
试运行也会保存已收录链接，正式运行将跳过这些链接；阅读首次试运行简报即可看到它们。

定时已写在工作流中，提交到默认分支后，计划每周一、三、五、日北京时间09:00处理全部25个账号。
GitHub调度可能延迟。试运行不会关闭定时：如果需要先测试几天，把工作流中schedule及其cron两行删除，保留workflow_dispatch。
工作流并不依赖本机开机。仓库默认分支必须保留工作流文件。

## 阅读和保留结果

- reports/情报简报_日期_时间_运行编号_尝试次数.md：每次运行的报告，避免同日重复运行覆盖。
- reports/latest_status.json：最近一次诊断，无完整文章正文和密钥。
- state/seen_articles.json：已写入报告的链接去重记录。不要删除，除非明确要重新收录历史文章。
- 每次运行的Artifacts也保留报告备份30天；仓库内报告不受这个30天限制。
- 服务部分失败也会尽量保留其他账号的结果，最后一个步骤会将运行标为失败以提醒检查。

若git推送失败，先从Actions的Artifacts下载备份；修复权限后重新运行。
分支保护或组织策略可能禁止机器人直接推送。不要为此盲目关闭保护，可改为上传备份或通过PR保存结果。

## 第一版的证据规则

1. “最近2天”明确按北京时间昨日00:00至本次执行时刻计算，不声称为滚动48小时。
2. Tavily日期可能是更新时间或估计日期，仅作检索参考，不直接作为原始发布日期。
3. 微信脚本优先读取页面发布时间；其他来源需要模型提供正文内的发布日期证据片段，程序核对片段和日期是否对应。
   模型仍可能误认日期，所以报告明确标记“模型识别，建议复核”。
4. 日期未知/超出范围的B–E类不作为新条目，失败原因保留在检索记录中。
5. A类仅允许标题明确含目标期刊名及期号/目录的较早或日期未知线索，单列待核实，不宣称为最新一期或近两天新发布。
6. 仅有搜索摘要时不生成完整文章简述。微信脚本被验证页拦截但Tavily有正文时可使用后者，并标明。
7. 只有微信正文成功读取、页面js_name账号标签与目标账号名规范化后相同，才标记确认来自该号；不依据文章作者署名判断。
   当前未维护期刊官方域名白名单，因此期刊官网条目也可能保守标记未确认，仍需人工复核。
8. 账号身份未确认的近似结果不会证明该公众号实际更新。若希望精确跟踪，后续需补齐账号标识/样例链接并建立可信源列表。
9. 每账号最多分析5个搜索候选、收录3条，总计25条。先给各账号一个名额，再轮转补位；不保证召回全部新文章。相关领域条目单列，不表示目标账号已更新。
10. 不保存全文正文到仓库，保留来源链接、简述、诊断与去重记录。

普通网页通过Tavily返回正文；本版没有额外安装下载插件。正文/摘要发送给DeepSeek生成内容。
跨来源趋势要求至少引用两个不同账号；证据不足时少写或留空，不凑足3条。

## 常见故障

- HTTP401/403：检查对应Secret的名称和值以及服务账号权限。
- HTTP402/429/432等：检查提供商余额、额度、限流或当前服务说明。
- DeepSeek模型不可用：查看官方模型列表，在Variables里设置DEEPSEEK_MODEL。
- 微信读取失败：可能是验证页/网络阻断，不能保证云端可读，不尝试绕过验证。
- 保存步骤403：检查仓库Settings → Actions → General中的工作流写权限及组织策略。
- 没有Run workflow按钮：确认工作流在默认分支的.github/workflows/digest.yml，且Actions未禁用。
- 只有试运行3个账号的结果：查看账号数；定时运行默认25个，手动可选25。

本地离线验证（不调用API）：

```text
python -m unittest discover -s tests -v
```

官方接口参考：

- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://api-docs.deepseek.com/
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
