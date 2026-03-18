# TODO

## Phase 1: 项目初始化
- [ ] 初始化 backend 目录结构
- [ ] 配置数据库连接
- [ ] 创建基础 FastAPI 应用
- [ ] 确认 `/docs` 可正常访问

## Phase 2: 企业基础信息管理
- [ ] 创建 Company 数据模型
- [ ] 创建 Company schema
- [ ] 创建 Company CRUD
- [ ] 实现新增企业接口
- [ ] 实现企业列表接口
- [ ] 实现企业详情接口

## Phase 3: 股权结构管理
- [ ] 创建 ShareholderStructure 模型
- [ ] 实现股权关系录入接口
- [ ] 实现股权关系查询接口

## Phase 4: 控制关系分析
- [ ] 基于 NetworkX 构建股权关系图
- [ ] 实现基础股权穿透分析
- [ ] 实现控制链条展示

## Phase 5: 国别归属判定
- [ ] 创建 CountryAttribution 模型
- [ ] 实现实际控制地判定规则
- [ ] 支持特殊结构标记

## Phase 6: 业务线标注
- [ ] 创建 BusinessSegment 模型
- [ ] 实现业务线录入接口
- [ ] 支持主营业务和新兴业务区分

## Phase 7: 征订与日志
- [ ] 创建 AnnotationLog 模型
- [ ] 实现修改记录功能
- [ ] 支持版本记录

## Phase 8: LLM 辅助模块
- [ ] 设计业务线识别输入输出格式
- [ ] 实现基础 LLM 调用接口
- [ ] 实现解释生成接口