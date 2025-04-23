# 知识存储工具 (StoreKnowledgeTool) 文档

## 功能概述

知识存储工具是一个用于将各种信息永久存储到知识库中的工具。它允许用户通过自然语言指令保存重要信息，并提供了标签分类、重要度标记、知识关联、知识验证和知识图谱等高级功能。该工具继承自 `BaseTool` 基类，遵循 MaiBot 的工具系统架构。

## 主要功能

知识存储工具提供以下核心功能：

1. **存储知识** - 允许用户将搜索结果、总结或其他重要信息存储到知识库中
2. **自动去重** - 通过语义相似度检查避免存储重复内容
3. **内容更新** - 支持更新已有的相似内容，而不是创建新内容
4. **知识分类** - 通过标签系统对知识进行分类
5. **优先级管理** - 通过重要度标记对知识进行优先级排序
6. **知识关联** - 支持在不同知识条目之间建立关联关系
7. **知识验证** - 对存储的知识进行事实性验证，避免错误信息
8. **实体抽取** - 自动从内容中提取实体和关系
9. **知识图谱** - 构建不同实体之间的语义关系图谱

## 参数说明

知识存储工具接受以下参数：

| 参数名 | 类型 | 描述 | 是否必需 |
|-------|------|------|---------|
| query | string | 原始查询内容 | 是 |
| content | string | 要存储的知识内容 | 是 |
| source | string | 知识来源，如web_search、user_input、summary等 | 否，默认为user_input |
| timestamp | number | 时间戳 | 否，默认为当前时间 |
| tags | array | 知识标签，用于分类 | 否 |
| importance | integer | 重要程度，1-5，数字越大表示越重要 | 否，默认为3 |
| related_to | string | 关联的其他知识ID | 否 |
| override_similar | boolean | 是否覆盖相似内容，默认为false | 否 |
| verify_facts | boolean | 是否验证知识中的事实，默认为true | 否 |
| extract_entities | boolean | 是否提取实体和关系用于知识图谱，默认为true | 否 |

## 使用示例

### 1. 存储基本知识

```python
# 存储一条基本知识
function_args = {
    "query": "什么是人工智能",
    "content": "人工智能是计算机科学的一个分支，致力于创建能够模拟人类智能的系统。"
}

result = await store_knowledge_tool.execute(function_args)
```

### 2. 使用标签和重要度存储知识

```python
# 使用标签和重要度存储知识
function_args = {
    "query": "深度学习简介", 
    "content": "深度学习是机器学习的一个子集，使用多层神经网络进行数据处理和模式识别。",
    "tags": ["AI技术", "机器学习", "神经网络"],
    "importance": 5  # 最高重要度
}

result = await store_knowledge_tool.execute(function_args)
```

### 3. 更新现有知识

```python
# 更新现有的相似知识
function_args = {
    "query": "深度学习更新", 
    "content": "深度学习是使用人工神经网络的机器学习方法，它模仿人脑结构和功能，可以从大量数据中学习复杂模式。",
    "override_similar": True  # 覆盖相似内容
}

result = await store_knowledge_tool.execute(function_args)
```

### 4. 关联知识存储

```python
# 存储关联知识
function_args = {
    "query": "CNN网络", 
    "content": "卷积神经网络(CNN)是深度学习中常用的一种网络结构，特别适合于图像识别和处理任务。",
    "tags": ["AI技术", "神经网络", "CNN"],
    "importance": 4,
    "related_to": "existing_knowledge_id"  # 关联到现有知识
}

result = await store_knowledge_tool.execute(function_args)
```

### 5. 使用知识验证功能

```python
# 存储知识并进行事实验证
function_args = {
    "query": "科学事实", 
    "content": "人工智能研究始于20世纪50年代，图灵测试由艾伦·图灵于1950年提出。",
    "verify_facts": True  # 启用事实验证
}

result = await store_knowledge_tool.execute(function_args)
```

### 6. 使用实体抽取和知识图谱功能

```python
# 存储知识并提取实体关系
function_args = {
    "query": "AI公司信息", 
    "content": "谷歌公司位于美国，它广泛使用深度学习技术。谷歌的TensorFlow是一个流行的深度学习框架。",
    "extract_entities": True  # 启用实体和关系抽取
}

result = await store_knowledge_tool.execute(function_args)

# 查询知识图谱中的关系
entity = "深度学习"
graph_results = await store_knowledge_tool.search_knowledge_graph(entity)
```

## 自然语言使用

知识存储工具设计为可以通过自然语言指令使用。以下是一些示例：

- "帮我记住一个重要知识：人工智能是计算机科学的一个分支，致力于创建能够模拟人类智能的系统。"
- "请将这条信息作为重要知识储存并标记为AI技术：深度学习是机器学习的一个子集，使用多层神经网络进行数据处理和模式识别。"
- "请更新之前关于深度学习的知识：深度学习是使用人工神经网络的机器学习方法，它模仿人脑结构和功能，可以从大量数据中学习复杂模式。"
- "记录这个事实并验证它的准确性：谷歌的AlphaGo在2016年击败了围棋世界冠军李世石。"

LLM会解析这些自然语言指令并转换为适当的工具调用。

## 实现详情

### 核心方法

工具实现了以下核心方法：

- `execute()` - 主入口方法，处理知识存储逻辑
- `_check_similar_content()` - 检查是否存在相似内容，避免重复存储
- `_ensure_indexes()` - 确保必要的数据库索引存在
- `search_knowledge()` - 搜索知识库中的内容
- `_verify_facts()` - 验证知识内容的事实性
- `_extract_entities_and_relations()` - 从知识内容中提取实体和关系
- `_update_knowledge_graph()` - 更新知识图谱
- `search_knowledge_graph()` - 搜索知识图谱中的关系
- `_update_reverse_relation()` - 更新知识之间的双向关联

### 知识验证机制

知识验证功能通过以下步骤实现：

1. 解析知识内容并检查是否包含明显错误的信息
2. 根据配置的验证规则匹配可能的错误内容
3. 为验证结果分配置信度分数
4. 如果置信度较高且确认为错误信息，阻止存储
5. 将验证结果一同存储，以便后续参考

在实际应用中，可以将验证功能扩展为调用专门的事实验证API或服务。

### 知识图谱构建

知识图谱功能通过以下步骤实现：

1. 从知识内容中提取实体（如人物、组织、地点、技术名词等）
2. 识别实体之间的关系（如"位于"、"创建"、"使用"等）
3. 将实体和关系存储到知识图谱集合中
4. 建立索引以支持快速查询
5. 提供接口以实体为中心查询相关关系

### 存储机制

知识存储使用MongoDB数据库：

- 使用嵌入向量存储内容的语义表示
- 使用余弦相似度进行相似内容检测
- 创建索引以优化查询性能
- 使用独立集合存储知识图谱关系

### 错误处理

工具实现了全面的错误处理机制：

- 参数验证 - 检查必需参数是否存在和有效
- 嵌入向量获取错误处理
- 数据库操作错误处理
- 知识验证错误处理
- 实体抽取错误处理

所有操作都包含在try-except块中，确保任何错误都能被适当地捕获和处理。

## 数据结构

### 知识条目

存储在数据库中的知识条目包含以下字段：

- `content` - 知识内容
- `embedding` - 内容的嵌入向量
- `query` - 原始查询
- `source` - 知识来源
- `created_at` - 创建时间
- `updated_at` - 更新时间
- `importance` - 重要程度（1-5）
- `access_count` - 访问计数
- `tags` - 标签数组
- `related_to` - 关联知识ID数组
- `verification` - 验证结果对象（包含is_factual、confidence、reason等字段）
- `entities` - 提取的实体数组
- `relations` - 提取的关系数组

### 知识图谱节点

存储在knowledge_graph集合中的关系节点包含以下字段：

- `subject` - 主体实体
- `predicate` - 关系谓词
- `object` - 客体实体
- `source_knowledge_id` - 来源知识ID
- `created_at` - 创建时间

## 使用建议

1. **使用标签分类** - 为知识添加相关标签，以便更容易地组织和检索
2. **设置适当的重要度** - 根据知识的重要性设置1-5的等级
3. **关联相关知识** - 对相关的知识条目建立关联关系
4. **覆盖过时内容** - 使用`override_similar`参数更新过时的知识
5. **启用事实验证** - 保持验证功能开启，防止错误信息混入知识库
6. **检索知识图谱** - 使用`search_knowledge_graph`方法探索实体之间的关系网络

## 扩展建议

以下是一些可能的扩展方向：

1. **高级知识验证** - 接入专业的事实验证API或服务
2. **自动标签生成** - 使用NLP模型自动为知识生成标签
3. **知识推理** - 基于已有关系推断可能的新关系
4. **过期机制** - 为知识添加过期日期，定期审查过时知识
5. **用户权限** - 添加对不同用户的存储权限控制
6. **可视化界面** - 为知识图谱提供交互式可视化界面

## 测试

可以使用以下文件来测试知识存储工具的各项功能：

- `src/do_tool/tool_can_use/examples/store_knowledge_example.py` - 测试基本存储、标签和重要度、相似内容检测等功能
- `src/do_tool/tool_can_use/examples/knowledge_validation_and_graph_example.py` - 测试知识验证和知识图谱功能 