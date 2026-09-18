# T7 手把手指南：搭 Dify 工作流

这份是给你**自己操作**用的。计划文档里那份是给实现者看的。

全程大约 1 小时。做完之后告诉我，我接着写 T8 / T13 / T14。

---

## 总览：你要准备三样东西

| 东西 | 用在哪 | 花费 |
|---|---|---|
| 飞书机器人 Webhook | 推送日报到手机 | 免费 |
| DeepSeek API Key | 让 Dify 能调用大模型 | 几块钱，能用大半年 |
| Dify 账号 + 工作流 | 本项目的大脑 | 免费额度够每天跑一次 |

**顺序建议：先飞书（最简单）→ 再 DeepSeek → 最后 Dify。** 前面两步各 5 分钟，做完再去啃 Dify。

---

# 第一步：飞书机器人（约 5 分钟）

1. 打开飞书，**新建一个群**（可以只有你自己一个人，比如叫「每日情报」）

2. 进群 → 右上角 **设置**（齿轮图标）→ **群机器人** → **添加机器人** → 选 **自定义机器人**

3. 起个名字，比如 `情报助手`，点添加

4. **安全设置这一步很关键**：勾选 **自定义关键词**，填：

   ```
   每日情报
   ```

   > 为什么填这个：飞书要求机器人至少有一种安全设置。选了「关键词」之后，**消息里必须包含这个词才发得出去**。我们生成的日报标题固定是 `📊 每日情报 · 日期`，降级告警也是同样开头，所以这个词一定命中。
   >
   > ⚠️ 不要选「IP 白名单」——GitHub Actions 的出口 IP 是变化的，会被拦。

5. 复制 **Webhook 地址**，形如：
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/一串字符
   ```

6. **先记到记事本里**，后面好几处要用。

### 顺手验证一下

复制下面这行到终端，把 URL 换成你的：

```bash
curl -s -X POST "你的webhook地址" \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"每日情报 测试消息"}}'
```

飞书群里应该立刻出现这条消息。返回 `{"code":0,...}` 就是成功。

> 注意 `每日情报` 这四个字不能省，否则会被关键词安全设置拦下，返回错误码。

---

# 第二步：DeepSeek API Key（约 5 分钟）

1. 打开 `https://platform.deepseek.com`，注册并登录

2. 左侧 **充值**，充 **10 元**（本项目每天跑一次，消耗约 2 万 token，10 元够用很久）

   > DeepSeek 好像有最低充值限制，按页面提示来。

3. 左侧 **API keys** → **创建 API key** → 起名（比如 `daily-intel`）

4. **立刻复制**——这个 key 只显示一次，关掉就再也看不到了，形如 `sk-xxxxxxxx`

5. 记到记事本里

---

# 第三步：Dify 工作流（约 40 分钟）

## 3.1 注册并创建工作流

1. 打开 `https://cloud.dify.ai`，注册登录

2. 点 **创建应用** → 应用类型选 **工作流（Workflow）**

   > ⚠️ **一定要选 Workflow，不要选 Chatflow。** 两者界面像但节点类型不同，选错后面会卡住。如果免费版里找不到 Workflow 选项，停下来告诉我。

3. 名字填 `daily-intel`，点创建。你会看到一个空白画布。

## 3.2 配置模型

> ⚠️ **Dify 改过版，这一节的入口新旧版本不同。** 按下面的顺序找，找到哪个是哪个。

**入口在哪（按顺序试）：**

1. **「集成」/「Integrations」** → **模型供应商 / Model Provider**（新版入口）
2. **「市场」/「Marketplace」** → **模型（Model）** 分类 → 搜 `DeepSeek` → **安装**
3. 右上角**头像** → **设置 / Settings** → 左侧菜单里的 **模型供应商**（旧版入口）

**然后**：在 DeepSeek 卡片上点 **设置/Setup**，把第二步的 API Key 粘进去，保存。Dify 会先验证凭据，通过后所有应用都能用。

**两种常见情况：**

| 现象 | 处理 |
|---|---|
| 显示「尚未安装模型供应商」 | 去市场搜 `DeepSeek` 安装最新版 |
| 市场里搜不到 DeepSeek | 装 **「OpenAI-API-Compatible」** 通用供应商，端点填 `https://api.deepseek.com`，模型名填 `deepseek-chat` |

**实在找不到就先跳过这一节**，直接往下搭 3.3–3.6 的节点。等你在 3.5 加 LLM 节点、点模型下拉框时，如果没有可选模型，下拉框旁边通常就有齿轮图标或「去配置」，点它一样能进来。

配好后回到工作流画布，点 **开始节点**（默认就有一个），在右侧。

## 3.3 搭开始节点

开始节点里添加两个**输入变量**（点「+ 添加变量」）：

| 变量名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `raw_items` | String（字符串） | 是 | 采集到的新闻，JSON 文本 |
| `date` | String（字符串） | 是 | 形如 `2026-09-17` |

## 3.4 加代码节点「预筛」

1. 点开始节点右侧的 **+**，添加 **代码** 节点

2. 节点名改成 `预筛`

3. **输入变量**：添加一个 `raw_items`，类型 String，值选择 **开始节点的 raw_items**（用下拉选，不要手打）

4. **输出变量**：添加一个 `items`，类型 **String**

5. 语言选 **Python3**，把下面的代码整个粘进去：

```python
import json

def main(raw_items: str) -> dict:
    try:
        items = json.loads(raw_items)
    except Exception:
        return {"items": "[]"}

    cut = []
    for it in items:
        content = (it.get("content") or "").strip()
        title = (it.get("title") or "").strip()
        if not content and not title:
            continue
        cut.append({
            "title": title[:200],
            "content": content[:800],
            "url": it.get("url", ""),
            "source": it.get("source", ""),
            "category": it.get("category", ""),
            "published_at": it.get("published_at", ""),
        })
        if len(cut) >= 60:
            break

    return {"items": json.dumps(cut, ensure_ascii=False)}
```

> 这段做两件事：**去空条目**，以及**把每条截断到 800 字、总共最多 60 条**——控制 token 消耗。没有它，一次可能烧掉几十万 token。

## 3.5 加 LLM 节点 A「结构化抽取」

1. 在预筛节点右侧点 **+**，添加 **LLM** 节点，改名 `结构化抽取`

2. **模型**：选 `deepseek-chat`

3. **温度**：调到 `0.1`（越低越稳定，这个节点要的是准确的判断不是创意）

4. **SYSTEM 提示词**（整个粘进去）：

````
你是金融与 AI 新闻分析助手。输入是一批新闻条目（JSON 数组）。请对每一条输出结构化分析。

对每条新闻输出一个对象，字段如下：

- event_type：从以下枚举中选且只能选一个，禁止自创：
  货币政策 | 经济数据 | 地缘政治 | 央行购金 | 美元走势 | 通胀 | 就业 | 其他
  判定规则：
  * 利率决议、官员表态、缩表扩表 → 货币政策
  * GDP、PMI、零售销售等非通胀非就业数据 → 经济数据
  * 战争、制裁、选举、贸易摩擦 → 地缘政治
  * 央行买卖黄金、黄金储备变动 → 央行购金
  * 美元指数、美债收益率 → 美元走势
  * CPI、PCE、物价 → 通胀
  * 非农、失业率、初请失业金 → 就业
  * 无法归入上述任何一类 → 其他

- direction：利多金银 | 利空金银 | 中性
  判定：提升实际利率预期 → 利空金银；压低实际利率预期 → 利多金银；
  避险需求上升 → 利多金银；与金银无关 → 中性

- strength：1 到 5 的整数。1=影响微弱，3=中等，5=重大冲击

- relevant：布尔值。该条是否与金银走势相关。AI 技术类新闻填 false

- summary：一句话中文摘要，不超过 40 字

- source / url / published_at：原样保留输入中的对应字段

只输出 JSON 数组，不要输出任何解释文字或 Markdown 代码块标记。
输出数组的长度必须与输入一致，且顺序一一对应。
````

5. **USER 提示词**：变量要**插进提示词输入框里**，不是填在别的字段。做法见下面方框。

> **变量怎么插**：
> 1. 看提示词输入框的工具栏，找 **`{x}` 图标** 或写着 **「变量」** 的按钮（位置各版本不同，可能在输入框上方或右下角）
> 2. 点它 → 弹出上游节点的变量列表 → **选，不要手打**
> 3. 有的版本可以直接在输入框里打一个 `{`，会自动弹出候选
>
> 插进去后长成 `{{#一串字符.items#}}`，那串字符是节点 ID，不用管对错，只要选的**节点名**对就行。

### ⚠️ 两种界面布局，看你的是哪种

**布局 A：分开的「系统提示词」和「用户提示词」两个框**

- 系统提示词框：整段规则照抄，**不含任何变量**
- 用户提示词框：**只放一个变量**，别的什么都不写

**布局 B：只有一个提示词框**（Workflow 应用常见）

- 把整段规则放进这**一个**框，然后**在最后单独加一行**放变量：

```
（整段规则照抄）

只输出 JSON 数组，不要输出任何解释文字或 Markdown 代码块标记。
输出数组的长度必须与输入一致，且顺序一一对应。

{{#预筛.items#}}
```

效果和分开写一样——模型看到的本来就是一段拼起来的文本。

**不确定自己是哪种？截个图最快。**

   > Dify 的 LLM 节点输出变量名固定叫 `text`，改不了。这没关系——最后在结束节点统一改名（3.7 会说）。

> **关于「上下文（Context）」那一栏**：两个 LLM 节点都会有这个可选项，界面可能提示「请启用上下文功能，请在提示中填写上下文变量」。
>
> **留空，不要启用。** 那是给 RAG／知识库检索用的——先上传文档建知识库，检索出片段再喂给模型。我们的新闻是通过变量直接传进 USER 提示词的，不经过知识库。那只是引导提示，不是报错。

## 3.6 加 LLM 节点 B「日报生成」

1. 在「结构化抽取」右侧点 **+**，再加一个 **LLM** 节点，改名 `日报生成`

2. **模型**：`deepseek-chat`

3. **温度**：调到 `0.3`（要稍微有点表达力）

4. **SYSTEM 提示词**：

````
你是金银与 AI 情报编辑。根据输入的结构化事件列表，生成一份中文日报。

输出严格 JSON，结构如下：

{
  "ai_news": [{"title": "标题", "why": "为什么重要", "url": "链接"}],
  "gold_news": [{"summary": "事件摘要", "direction": "利多金银", "strength": 4, "url": "链接"}],
  "gold_conclusion": "一句综合判断",
  "calendar": [{"time": "20:30", "event": "美国 8 月 CPI 同比"}]
}

要求：
- ai_news：挑 3 到 5 条与 AI 技术、模型、行业相关的（relevant 为 false 的那些）。
  why 字段用一句话说明为什么值得关注，不超过 40 字
- gold_news：挑 3 到 5 条与金银最相关的（relevant 为 true），按 strength 从高到低排列
- gold_conclusion：结合当日事件给出一句多空倾向判断，不超过 60 字
- calendar：只填输入中明确提到的今日宏观事件；没有就填空数组 []
- **严禁编造输入中不存在的信息**，url 必须来自输入
- 只输出 JSON，不要输出 Markdown 代码块标记
````

5. **USER 提示词**：用 `{x}` 图标插入 **「结构化抽取」节点的 text**

## 3.7 配置结束节点（最容易搞错的一步）

1. 找到画布上的 **结束** 节点（默认就有，在最右侧）

2. 添加两个**输出变量**，都是 **String（字符串）** 类型：

| 输出变量名 | 值（用 `{x}` 图标选择） |
|---|---|
| `events_json` | 「结构化抽取」节点的 `text` |
| `digest_json` | 「日报生成」节点的 `text` |

> ⚠️ **这两个名字必须一字不差。** 我的 Python 代码就是按这两个名字去取的，写错会报「缺少 events_json」。
>
> ⚠️ 这里容易犯的错：变量名填对了但值没选对节点。`events_json` 要对应**结构化抽取**，`digest_json` 对应**日报生成**，别选反。

3. 点右上角 **运行/预览**，随便造一条输入试试能不能跑通。跑不通先别导出，告诉我报什么错。

## 3.8 导出 DSL（备份用）

右上角 **···** → **导出 DSL** → 保存到：

```
D:\金银舆情监控\dify\daily-intel-workflow.yml
```

> `dify` 目录可能还不存在，自己建一个。这个文件之后会提交进仓库——它是工作流的备份，误删或改坏了可以导入还原。

## 3.9 创建 API Key

在应用的 **访问 API** 页面（左侧菜单），点 **创建 API 密钥**，复制出来，形如 `app-xxxxxxxx`。

---

# 第四步：验证（约 10 分钟）

## 4.1 用 curl 调一次

在终端里逐段执行：

```bash
cd "D:/金银舆情监控"
export DIFY_API_KEY="app-你刚才复制的key"

python - <<'PY'
import json, pathlib
items = [{
    "title": "美联储官员放鸽",
    "content": "沃勒表示年内可能进一步降息",
    "url": "https://x.com/1",
    "source": "金十数据快讯",
    "category": "finance",
    "published_at": "2026-09-15T10:00:00+08:00",
}]
payload = {
    "inputs": {"raw_items": json.dumps(items, ensure_ascii=False), "date": "2026-09-15"},
    "response_mode": "blocking",
    "user": "daily-intel",
}
pathlib.Path("samples/_tmp_payload.json").write_text(
    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
)
PY

curl -s -X POST "https://api.dify.ai/v1/workflows/run" \
  -H "Authorization: Bearer $DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  --data @"samples/_tmp_payload.json" \
  -o samples/_tmp_response.json

python -m json.tool samples/_tmp_response.json
```

> `samples` 目录不存在的话自己建一个。

## 4.2 检查这三条（全过才算成功）

看输出里的 `data` 部分：

1. **`status` 是 `"succeeded"`** —— 不是的话把 `error` 内容发我
2. **`events_json` 能看出是个 JSON 数组**，每条含 `event_type`、`direction`、`strength`、`relevant`、`summary`
3. **`event_type` 的取值都在枚举里**（货币政策/经济数据/地缘政治/央行购金/美元走势/通胀/就业/其他），`direction` 是「利多金银」「利空金银」「中性」之一

## 4.3 留下样本文件

三条都过了就执行：

```bash
cd "D:/金银舆情监控"
mv samples/_tmp_response.json samples/dify_response.json
rm -f samples/_tmp_payload.json
```

> 这个文件后续有两个用途：我写 T8 时用它做离线测试，跑 `--offline` 模式也用它。
> 提醒一句：它会被提交进公开仓库。里面只有新闻文本和 token 计数，**不含密钥**，可以公开。

---

# 做完之后

告诉我三件事：

1. 飞书测试消息**收到了吗**（第一步验证那条）
2. Dify 的 curl 验证**三条都过了吗**，没过的话把报错贴给我
3. `samples/dify_response.json` **存好了吗**

然后我接着做 T8（Dify 客户端）、T13（主流程）、T14（上线）。

---

# 卡住了怎么办

| 现象 | 多半是 |
|---|---|
| 飞书返回 `code` 非 0，提示关键词不匹配 | 消息里没带 `每日情报`。重发时把它加进 `text` |
| Dify 里找不到 Workflow 选项 | 免费版限制。告诉我，我们商量换方案 |
| 代码节点报 `ModuleNotFoundError` | 语言选成 Node.js 了，改回 Python3 |
| 结束节点报「缺少 events_json」 | 3.7 的变量名拼错了，或者值选成了别的节点 |
| curl 返回 401 | API Key 不对，或者 `export` 没生效（换个终端窗口要重新 export） |
| curl 返回 `status: failed` | Dify 里点「运行」看哪个节点报的错，把那一步的报错发我 |

**任何一步卡住都可以直接问我，不用自己硬扛。**
