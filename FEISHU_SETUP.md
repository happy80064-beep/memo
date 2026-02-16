# MemOS 飞书集成指南

## 一、创建飞书应用

### 1.1 访问飞书开放平台
- 打开 https://open.feishu.cn/app
- 登录您的飞书账号
- 点击"创建企业自建应用"

### 1.2 填写应用信息
- **应用名称**: MemOS AI助手
- **应用描述**: 您的个人AI记忆助手
- **应用图标**: 上传一个图标
- **可见范围**: 选择需要使用的成员

## 二、配置应用权限

### 2.1 权限管理
在应用后台，进入"权限管理"，添加以下权限：

**消息与群组权限：**
- `im:chat:readonly` - 获取群组信息
- `im:message:send` - 发送消息
- `im:message.group_msg` - 接收群消息
- `im:message.p2p_msg` - 接收单聊消息

**用户权限：**
- `contact:user.department:readonly` - 获取用户部门信息
- `contact:user.base:readonly` - 获取用户基本信息

### 2.2 事件订阅配置
进入"事件订阅"页面：

1. **加密方式**: 选择"加密"（推荐）
2. **验证令牌**: 复制生成的Token到 `FEISHU_VERIFICATION_TOKEN`
3. **加密密钥**: 复制生成的Key到 `FEISHU_ENCRYPT_KEY`

**订阅事件添加：**
- `im.message.receive_v1` - 接收消息事件

**请求地址配置：**
```
https://memo03.zeabur.app/feishu/webhook
```

> 注意：将 `memo03.zeabur.app` 替换为您的实际域名

## 三、发布应用

### 3.1 版本管理与发布
1. 进入"版本管理与发布"
2. 点击"创建版本"
3. 填写版本号（如 1.0.0）和更新说明
4. 点击"申请发布"

### 3.2 审核与使用
- 企业管理员需要在飞书管理后台审核通过
- 审核通过后，应用会出现在应用商店

## 四、Zeabur部署配置

### 4.1 添加环境变量
在Zeabur控制台，为MemOS服务添加以下环境变量：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
```

### 4.2 修改启动命令（可选）

如果您想单独部署飞书机器人服务，可以创建一个新的Zeabur服务：

**方式1：和Web服务共用（推荐）**
直接部署到现有Web服务，飞书回调路径为 `/feishu/webhook`

**方式2：独立部署**
创建新的Zeabur服务，启动命令：
```bash
python feishu_bot.py
```

## 五、使用飞书机器人

### 5.1 私聊使用
1. 在飞书搜索"MemOS AI助手"
2. 点击开始私聊
3. 直接发送消息即可与AI对话

### 5.2 群聊使用
1. 在群聊中点击"设置" -> "添加应用"
2. 选择"MemOS AI助手"
3. @机器人即可对话：
   ```
   @MemOS AI助手 明天我要和团队开会讨论项目
   ```

### 5.3 记忆功能
- 飞书中的对话会自动存入MemOS的L0缓冲区
- 每次对话都会关联到同一个`session_id`
- AI会记住之前的对话内容

## 六、故障排查

### 6.1 检查Zeabur日志
```
[Feishu] 收到消息: ...
[Feishu] 用户: ou_xxxxxxxx, 会话: feishu-p2p-ou_xxxxxxxx
[Feishu] 回复已发送
```

### 6.2 常见问题

**Q: 飞书收不到回复？**
- 检查Zeabur日志是否有错误
- 确认FEISHU_APP_ID和FEISHU_APP_SECRET正确
- 确认应用已发布并通过审核

**Q: 消息重复？**
- 检查事件订阅是否配置了多个相同的URL
- 检查Zeabur是否部署了多个实例

**Q: 机器人不响应@消息？**
- 确保群聊中已添加机器人应用
- 检查权限管理中是否添加了`im:message.group_msg`

## 七、安全建议

1. **验证Token**: 始终配置`FEISHU_VERIFICATION_TOKEN`，防止伪造请求
2. **加密传输**: 启用飞书的加密模式，配置`FEISHU_ENCRYPT_KEY`
3. **IP白名单**: 在飞书后台配置Zeabur的IP白名单（可选）

---

如有问题，请检查Zeabur运行日志或联系开发者。
