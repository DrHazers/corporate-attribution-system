# Corporate Attribution System - 产业分析模块说明文档

## 一、模块定位

产业分析模块用于描述企业“在做什么业务”以及“属于哪个行业”，是对控制链分析的补充。

该模块采用三层结构：
- 业务事实层（business_segments）
- 行业映射层（business_segment_classifications）
- 留痕层（annotation_logs）

---

## 二、核心数据链路

companies
→ business_segments
→ business_segment_classifications
→ annotation_logs

---

## 三、表结构说明

### 1. business_segments（业务线表）

用途：描述公司业务构成

关键字段：
- id：主键
- company_id：关联 companies.id
- segment_name：业务名称
- segment_type：primary / secondary / emerging / other
- revenue_ratio：收入占比
- profit_ratio：利润占比
- is_current：是否当前业务
- confidence：置信度

说明：
- 每家公司 1~4 条业务线
- 至少 1 条 primary
- is_current=true 用于当前分析

---

### 2. business_segment_classifications（行业映射）

用途：将业务映射到标准行业（GICS）

关键字段：
- id
- business_segment_id：关联业务线
- standard_system：GICS
- level_1 ~ level_4：行业层级
- is_primary：主行业
- review_status：auto / manual_confirmed / manual_adjusted

说明：
- 每条业务线 1~2 条映射
- primary 业务必须有主行业

示例：
Consumer Discretionary > Retail > Broadline Retail > E-commerce

---

### 3. annotation_logs（留痕表）

用途：记录数据修改过程

关键字段：
- target_type：business_segment / business_segment_classification
- target_id：目标记录
- action_type：create / update / manual_override / confirm
- old_value / new_value：JSON
- operator：analyst / reviewer / system

说明：
- 用于可解释性
- 支持人工修订记录

---

## 四、模块能力

### 1. 业务结构分析
- 主营业务识别
- 收入结构拆分

### 2. 行业归属分析
- 主行业识别
- 多行业权重

### 3. 人工修正识别
- 是否有 manual_adjusted
- 是否需要审核

---

## 五、未来扩展方向

1. 自动行业分类（NLP）
2. 行业权重计算
3. 控制链 × 产业分析融合
4. 历史业务结构变化分析

---

## 六、总结

本模块实现：

“公司 → 业务 → 行业 → 留痕”的完整分析链路，

为产业研究提供结构化数据基础。
