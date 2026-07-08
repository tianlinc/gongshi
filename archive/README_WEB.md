# RDM 工时填报系统 - Web 版

一个现代化的 Web 界面工时填报工具，支持自动登录、工时填写和提交。

## 功能特点

- 🎨 **现代化界面** - Bootstrap 5 响应式设计，美观易用
- 🔐 **自动登录** - 自动处理 AES 加密认证
- 📊 **可视化界面** - 直观的工时填写表格
- 💾 **草稿保存** - 本地存储草稿，随时恢复
- 👁️ **预览功能** - 提交前预览工时汇总
- 📅 **周历显示** - 自动显示当前周信息

## 快速开始

### 方法 1：一键启动（推荐）

双击运行 `start.bat`，会自动：
1. 检查 Python 环境
2. 安装必要依赖
3. 启动 Web 服务器
4. 提示访问地址

### 方法 2：手动启动

1. 安装依赖：
```bash
pip install flask flask-cors requests pycryptodome
```

2. 启动服务器：
```bash
python app.py
```

3. 打开浏览器访问：`http://localhost:5000`

## 使用流程

### 1. 登录系统
- 输入用户名和密码（默认已填入配置的账号）
- 点击"登录"

### 2. 填写工时
- 点击"添加任务"创建新任务行
- 输入任务名称
- 为每天输入工时数（支持 0.5 小时为单位）
- 设置任务完成率

### 3. 快速操作
- **工时模板** - 点击"加载模板"快速填充预设任务
- **快速填充** - 点击"工作日每天8小时"自动填充
- **保存草稿** - 暂存当前填写的内容
- **清空所有** - 重新开始填写

### 4. 提交工时
1. 点击"预览"查看工时汇总
2. 确认无误后点击"提交工时"
3. 在预览窗口点击"确认提交"

## 目录结构

```
D:\code\gongshi\
├── app.py                  # Flask 主程序
├── start.bat               # 一键启动脚本
├── templates/              # HTML 模板
│   ├── login.html         # 登录页面
│   └── dashboard.html     # 工时填写主页
├── static/                 # 静态资源（可选扩展）
│   ├── css/               # 自定义样式
│   └── js/                # 自定义脚本
└── README_WEB.md          # 本说明文件
```

## 功能说明

### 登录认证
- 自动处理 RDM 系统的 AES-ECB 加密
- 支持会话管理
- 错误提示友好

### 工时填写
- **任务名称**：自由输入任务描述
- **每天工时**：支持 0-24 小时，步进 0.5 小时
- **完成率**：0-100%，用于标识任务进度
- **实时统计**：自动计算每个任务的小计和总计

### 数据管理
- **草稿保存**：使用 localStorage 存储在浏览器本地
- **自动恢复**：下次打开自动加载上次保存的内容
- **模板加载**：预设常用任务模板

## 注意事项

⚠️ **当前为演示版本**，需要根据实际系统调整：

1. **后端 API 集成**
   - 打开 `app.py`
   - 修改 `RDMClient` 类中的 `get_tasks()` 和 `submit_timesheet()` 方法
   - 根据实际 API 端点和数据格式调整

2. **工时页面 URL**
   - 需要探测实际的工时填报页面路径
   - 可使用 `test_login.py` 进行探测

3. **任务列表**
   - 当前返回模拟数据
   - 需要接入系统实际的任务查询接口

## 自定义和扩展

### 添加任务模板

编辑 `dashboard.html` 中的 `loadTemplate()` 函数：

```javascript
tasks = [
    { id: ++taskIdCounter, name: '任务1', hours: [8,8,8,8,8,0,0], rate: 100 },
    { id: ++taskIdCounter, name: '任务2', hours: [4,4,0,0,0,0,0], rate: 80 },
    // 添加更多...
];
```

### 修改样式

在 `templates/*.html` 的 `<style>` 标签中自定义 CSS：

- 修改配色方案：调整 `linear-gradient` 颜色值
- 调整布局：修改间距、圆角等样式
- 响应式适配：使用 Bootstrap 栅格系统

### 扩展功能

在 `app.py` 中添加新的路由：

```python
@app.route('/api/custom-function', methods=['POST'])
def custom_function():
    # 实现自定义逻辑
    return jsonify({"success": True, "data": result})
```

## 配置文件（可选）

创建 `config.py` 进行高级配置：

```python
class Config:
    DEBUG = True
    SECRET_KEY = 'your-secret-key'
    RDM_BASE_URL = 'http://10.111.36.3:2029'
    # 添加更多配置...
```

## 故障排查

### 问题：浏览器无法访问

**解决**：
- 检查防火墙设置
- 确认端口 5000 未被占用
- 尝试访问 `http://127.0.0.1:5000`

### 问题：登录失败

**解决**：
- 检查用户名密码是否正确
- 查看控制台错误日志
- 运行 `test_login.py` 测试登录逻辑

### 问题：工时提交失败

**解决**：
- 检查 Network 标签中的请求响应
- 确认后端 API 是否正确对接
- 根据错误信息调整数据格式

## 开发者信息

- **技术栈**：Python Flask + Bootstrap 5 + Vanilla JavaScript
- **加密方式**：AES-ECB (Pkcs7 padding)
- **依赖库**：flask, flask-cors, requests, pycryptodome

## 许可证

内部工具，仅供公司内部使用。

---

💡 **提示**：首次使用建议先使用浏览器开发者工具（F12）分析系统实际的 API 接口，然后更新代码中的相应部分。
