# 管理员认证与配置保护

T25本地版本将看板与管理权限分开：公共只读看板无需登录，管理员必须通过服务端认证。原前端硬编码密码不再授权。未配置密码哈希时管理登录关闭（503），不影响公共查询。

## 本地配置

先备份数据库，再运行既有迁移命令：

```sh
backend/.venv/bin/python -m lottery.cli init-db
```

006迁移只添加`admin_sessions`和`login_throttles`表，不修改开奖、预测或评分。此轮开发没有替你执行实际业务库迁移。

在本机终端生成密码哈希：

```sh
backend/.venv/bin/python -m lottery.auth
```

工具使用隐藏输入，两次确认至少12位密码，只输出PBKDF2-SHA256哈希（随机16字节盐，600000次迭代）。不要把真实密码发到聊天或放入命令参数。

将哈希填入服务端 `backend/.env`，并重启API：

```dotenv
ADMIN_USERNAME=tian
ADMIN_PASSWORD_HASH=此处填生成的完整哈希
ADMIN_ORIGIN=http://127.0.0.1:9998
```

变量不能使用`VITE_`前缀，环境文件已被忽略，不提交到代码库。程序不会把哈希或Server酱密钥返回前端。本轮未配置真实管理员凭据。

`ADMIN_ORIGIN`必须与浏览器地址栏的协议、主机、端口完全一致，不含路径或尾部斜线。localhost与127.0.0.1是不同来源。HTTP仅接受回环地址，其他来源必须配置HTTPS，浏览器也必须实际通过HTTPS访问；云端公网HTTP看板仍可公开读，但不能沿用该地址启用管理登录。部署时需另行配置HTTPS或本地SSH隧道，不能通过伪造Origin解决。

## 会话与写保护

- `/api/auth/login`：POST JSON账号密码，校验精确Origin；登录尝试按服务端可见客户端地址每15分钟固定窗口最多10次（包括成功），计数在数据库原子递增。反向代理可能令多人共享额度；不是分布式抗攻击服务。上线时反向代理应覆盖转发地址头，Uvicorn仅信任实际代理，避免客户端伪造来源绕过限速。
- `/api/auth/session`：只读查询当前会话，未登录返回authenticated=false；有效会话返回账号、到期时间和CSRF令牌。
- `/api/auth/logout`：POST撤销数据库会话并删除cookie，必须有有效会话、正确Origin及`X-CSRF-Token`。失效会话返回401，前端按已失效处理。
- 令牌为32字节随机数，数据库只保存SHA256摘要，固定8小时过期，不滑动续期；退出删除令牌，旧cookie重放也无效。修改账号/密码哈希/Origin后旧会话失效（环境变更需重启进程）。
- Cookie为HttpOnly、SameSite=Strict、Path=/api；HTTPS配置下带Secure。本地回环HTTP模式不带Secure。
- 前端CSRF只保存在内存，不在localStorage/sessionStorage保存密码或管理授权。旧假登录存储值不被读取。
- FastAPI全局依赖保护所有已匹配路由的POST/PUT/PATCH/DELETE等非安全方法，登录仅豁免会话/CSRF但不豁免Origin。未登录写请求401，跨站或CSRF不符403。未来管理写接口默认继承，不得新建绕过全局依赖的子应用。
- GET/HEAD/OPTIONS只读开放。开发者必须保持GET无管理写副作用；仅在浏览器隐藏按钮不能替代服务端权限。

管理页面每分钟核对会话并按到期时间隐藏管理状态；服务端每个写请求实时校验，不依赖页面是否及时刷新。退出网络失败明确提示未确认，不能声称服务端已撤销。

## 范围

本轮提供T20所需的认证基础，没有开放训练任务创建、配置修改或数据修订功能。单管理员配置，不含账号注册、找回密码、多角色或MFA；修改配置需有服务器本身的权限。公网发布仍需按T29/T30进行HTTPS、备份、迁移及反向代理验收。
