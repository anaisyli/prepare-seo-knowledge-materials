# 企业知识资料初筛 Skill

`prepare-seo-knowledge-materials` 把已经提供到当前环境的企业原始资料（客户直接发来的文件、邮箱取料、电脑本地资料、WhatsApp 导出）筛成一个完整、可追溯的整理包，支持 SEO/GEO、建站、CRM、营销和培训等业务。

它做四件事：

1. 盘点全部资料，并把附件关联到所属邮件；
2. 打开每一份文件看内容，完成分类并提取知识点；
3. 用脚本把文件真实搬进对应文件夹，逐个校验；
4. 校验通过才算完成，不会出现“清单上有，包里没有”。

> 本 README 面向操作者。实际执行规则以 `SKILL.md` 和 `references/` 为准。

## 一、分类标准

先按最小内容单元判定 R0–R4，再汇总成整份资料的 A–E，最后打一个业务标签。一封邮件哪怕只有几句有用，也要把这几句提取出来。

### 1. 内容判定 R0–R4

| 判定 | 含义 |
| --- | --- |
| R0 可保留 | 公司自己的知识、能力、产品、材料、技术、流程，能脱离单次交易成立，对 SEO/GEO、建站、CRM、营销或培训有用 |
| R1 可提取 | 来自公司自己的流程、能力、产品、材料或技术描述，包括邮件和聊天里的说法。原文不保留，但能形成知识点 |
| R2 必须删除 | 个人信息、客户身份、价格、订单、付款、发货、客户专属规格 |
| R3 整体排除 | 合同、NDA、客户图纸、客户专属方案、成本利润、纠纷投诉 |
| R4 不确定 | 打不开、读不准、没人看过的图片、判断不了的内容 |

### 2. 文件处理 A–E

| 分类 | 动作 |
| --- | --- |
| A 原文保留 | 原样复制进 `A-原文保留/<标签>/` |
| B 待清理 | 复制进 `B-待清理/`，记录要删的位置，等批准后在副本上清理 |
| C 提取知识点 | 原文不保留，输出带来源定位的正式知识点，原件进 `来源文件/` 备查 |
| D 待定 | 打不开或判断不了，复制进 `D-待定/`，写清还缺什么 |
| E 排除 | 看过且没有可用内容，复制进 `E-排除/<标签>/`，写清具体原因（财务类除外） |

交易内容多不等于排除：先看有没有可提取的内容，提不出来才归 E。图片和音视频也按 A–E 分类，没人看过的图片是 D。

### 3. 业务标签

| 标签 | 内容 |
| --- | --- |
| 营销宣传 | 公司介绍、目录册、展会和宣传材料 |
| 业务场景 | 培训资料、FAQ、产品知识学习、客户案例 |
| 产品资料 | 产品清单、规格、面料材质、技术资料、证书 |
| 竞对资料 | 竞品和第三方资料，单独存放，不当公司事实 |
| SEO运营资料 | 关键词库、写作要求、页面规范 |
| 财务 | 账户、合同、发票、收汇、客户名单（**只登记，不复制**） |

交易往来、价格、无知识价值用于 E 类归档，不属于业务框架。

### 4. 知识点

知识点是正式知识，不需要二次审核，但必须写明适用范围：

| 范围 | 含义 |
| --- | --- |
| 通用 | 公司整体成立 |
| 某个款式 | 只适用于这个产品或款式 |
| 某次沟通 | 只在一次沟通里出现 |

单次沟通不能写成公司标准。例如一次报价出现 800 件，不能写成“标准 MOQ 800 件”。

### 5. 客户审核

筛选后由客户再看一遍。客户案例、能否公开不明确的内容会标记“待客户审核”，放进 `客户确认表.xlsx`，客户确认前不能当公司事实使用。如果只是文件里的一部分要确认，比如公司资料里的 3 个案例，就只标这部分，文件其余内容照常可用。

### 报价单怎么处理

报价单是带价格的产品资料，不再整份排除：保留款号、品名、成分、克重和图片，删除价格列、客户信息块、日期和订单信息，归为 B。纯订单或发货记录才归 E。

## 二、能力边界

**会做：**盘点并计算 SHA-256；打开文件判断内容；把文件搬进整理包并校验；标记敏感、交易、竞对内容；提取知识点；记录处理结果。

**不会做：**

- 不连接邮箱、不获取密码、不下载附件（取料在上游）；
- 不判断客户授权是否合法；
- 不绕过登录、权限或验证码；
- 不把单次订单、报价或沟通推广为标准价格、MOQ、交期或保证；
- 不转写音视频，不解压压缩包；
- 不写入生产知识库，不写 SEO 文章；
- 不编辑、覆盖、移动或删除原件。

## 三、调用方式

```text
使用 $prepare-seo-knowledge-materials 初筛 D:\SEO-Runs\<项目名>\原始资料。
我确认，这批资料可以用于本次知识库初筛，范围仅限本次提供的资料。
整理包输出到 D:\SEO-Runs\<项目名>\02_初筛包，工作文件放在 D:\SEO-Runs\<项目名>\_working。
不要修改源文件。
```

收集到的资料都复制进 `原始资料` 文件夹就行，不用改名，也不用分类。

“我确认……范围仅限……”这句不能省，缺了会在读取正文前停止。操作者不需要自报身份，也不需要手写 YAML 或日期。

已导出的接口数据把导出文件当输入即可。已授权连接器需在调用中写清读取范围、记录 ID 和版本字段。接口结构未知时，Skill 先给字段映射建议，确认后再分类。

## 四、标准流程

Skill 按这个顺序执行，都用自带脚本，不临时写脚本：

```powershell
# 1. 盘点，并把附件关联到邮件
python scripts/inventory_materials.py D:\Run\原始资料 `
  --output D:\Run\_working\inventory.json `
  --mail-manifest D:\Run\mail-manifest.json

# 2. 打开每份文件，记录能否读取
python scripts/extract_text.py D:\Run\_working\inventory.json --work D:\Run\_working

# 3. 有邮件时，挑出所有可能有用的句子，能力陈述句逐句读完
python scripts/mail_candidates.py D:\Run\_working\inventory.json --work D:\Run\_working `
  --sent-marker 发 --own-domain example.com

# 4. Skill 判断后写出 triage-results.json 和 knowledge-points.jsonl

# 5. 搬文件，生成全部清单
python scripts/build_package.py `
  --inventory D:\Run\_working\inventory.json `
  --triage D:\Run\_working\triage-results.json `
  --knowledge-points D:\Run\_working\knowledge-points.jsonl `
  --output D:\Run\02_初筛包

# 6. 校验，通过才算完成
python scripts/verify_package.py D:\Run\02_初筛包 `
  --extract-status D:\Run\_working\extract-status.json `
  --mail-candidates D:\Run\_working\mail-candidates.jsonl
```

只想先扫一遍做 Obsidian 目录时，第 1 步加 `--catalog <目录.md>` 即可。这一步只看文件名和大小，不读内容。

`--sent-marker` 和 `--own-domain` 用来只看公司自己写的内容：前者是已发送邮件标题的结尾标记，后者是公司邮箱域名，可以写多个。两个都不传时，会查看全部邮件内容。

### 常用选项

| 选项 | 用途 |
| --- | --- |
| `build_package.py --company <客户名>` | 显示在客户确认表的标题上 |
| `build_package.py --include-restricted` | 财务类也复制，放进 `E-排除/财务/` |
| `build_package.py --withhold <文件>` | 客户不让带走的文件名，一行一个 |
| `verify_package.py --accept-attachment-gaps <原因>` | 附件确实缺失且已接受时使用 |

## 五、整理包结构

```text
02_初筛包/
├── 00_总清单.md          # 先看这个
├── 客户确认表.xlsx        # 给客户审核，下拉选择
├── A-原文保留/
├── B-待清理/
├── C-知识点/
├── D-待定/
├── E-排除/
└── 审计记录/             # 含本机路径，不外发
```

图片、视频和大文件都放在各自的 A–E 文件夹里，超过 50MB 的文件在总清单里单独列出。`package-manifest.json` 和 `校验结果.json` 在 `审计记录/` 里。整理包内部受限，不能整包导入知识库，只有标记 `importable: true` 的资产才进入下一步。

## 六、校验会拦下什么

- 有文件没分类，或分类了但文件不在包里；
- 文件和原件哈希不一致；
- 包里多出清单没记录的文件；
- 清单里出现 `file:///` 或本机路径；
- 没打开过的文件被判了 A、B、C、E；
- 邮件没有经过全文或候选句审查就被排除；
- 含产品列或产品图的报价单被当成纯价格表排除，或被标成财务；
- 名字像收汇、发票、合同的文件被留在 A 或 B；
- B 类没有写具体删除位置；
- 客户案例没有进客户确认表；
- 只有部分内容待确认，却卡住整份文件；
- 财务以外的文件被标成“受限”；
- 来自单封邮件的知识点被写成“通用”、含有价格，或对不上公司发出的消息；
- E 类没有具体原因；
- 竞对或待客户审核的内容被标成公司事实；
- 待客户审核的内容没有进客户确认表；
- 附件缺失，或邮件没有对应的 `mail-manifest.json`，且没有写明接受原因。

校验没过时修问题后重建到新的空目录，不要手工改包。

## 七、B 类清理

初筛不修改任何文件。要清理 B 类时，批准需要明确指定 action ID，例如：

```text
批准 action-0001、action-0002。
拒绝 action-0003；action-0004 保持待定。
```

“看起来可以”、沉默或概括性请求都不算批准。执行前用 `scripts/verify_approved_plan.py` 校验批准记录、源文件哈希和目标路径。

## 八、格式说明

- **Excel：**检查隐藏工作表、批注和元数据，记录内嵌图片数量。`.xls` 通过 LibreOffice 转换后读取，打不开就归 D。
- **PDF：**先读文字层（需要 `pypdf`）。目录册和公司简介常是纯图片，AI 能看图时逐页查看，看不了再用 OCR，都不行才留在 D。
- **Word/PPT：**保留段落、幻灯片定位，检查备注、批注和文档属性。
- **图片：**可查看的尽量查看。从图片提取的知识点也要写适用范围，不从产品外观推断规格。
- **音视频、压缩包：**只登记并复制，归 D。

如果无法证明禁止内容已从可见文本、底层文本、备注、隐藏结构和元数据中移除，清理结果不能标记为可导入。

## 九、目录结构与测试

```text
prepare-seo-knowledge-materials/
├── SKILL.md
├── README.md
├── agents/openai.yaml
├── references/
│   ├── classification-policy.md
│   ├── format-handling.md
│   ├── input-contract.md
│   └── output-contract.md
├── scripts/
│   ├── inventory_materials.py
│   ├── extract_text.py
│   ├── mail_candidates.py
│   ├── client_review.py
│   ├── build_package.py
│   ├── verify_package.py
│   ├── package_common.py
│   └── verify_approved_plan.py
└── tests/
    ├── test_scripts.py
    └── test_package.py
```

```powershell
python -m unittest discover -s tests -v
```

脚本只依赖 Python 标准库。读取 PDF 文字层需要 `pypdf`，转换 `.xls/.doc/.ppt` 需要 LibreOffice；缺少时对应文件归 D，不会被排除。
