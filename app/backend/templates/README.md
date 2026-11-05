# 预置结构与辅助

版本：B-TIMED-KIT-2026-10-19。0004提供MaterialIssue，0005提供MaterialIssueOrder和明细外键；旧建表及成功请求缓存stub已移除。历史回填、普通单issueOrderId=null和查询适配均已预置，考生完成原子领退及同页交互。

scaffold_helpers仅提供run_atomic/cas_stock_delta。流水与审计直接复用models.py中的StockMovement/AuditLog；授权、数量、状态及完整事务仍由考生实现。两处权限筛选和本日日界缺陷保留为考题。

T2用AICallLog.original_suggestion/final_suggestion/decision/context保存原建议、最终计划和复核决定。replenishment-v1只接收inventory、issue_stats（TODAY）、knowledge、output_schema四个输入；示例不是实际查询或模型答案。分析、决定、结果读取均为501，AiPanel仅为表单参考。

0006清理空的旧草稿表；已有记录或自定义外键的旧表保留，不能通过删除历史迁移破坏现有库。新库不再含独立草稿表，T2无需新增表。T3由考生追加调拨表及确认唯一标识，无需任务平台。

tool-schema.stub.json仅供选用工具调用时参考，不强制tool_calls。SSE最低meta/progress/result/error及原令牌显式核对由考生实现，TransferPreview可作确认卡片参考，无独立手动调拨页。

本地模型内容故障使用fault_suggestion传入本次结构合法建议，fake_reference只篡改知识摘录；low_confidence为可选辅助。注入后仍检查真实实体、引用及权限，详见[故障说明](../../../contracts/testing/test-faults.json)。
