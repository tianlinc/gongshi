# 快速开始指南

## 第一步：安装依赖

双击运行 `install.bat`，或在命令行执行：

```bash
pip install requests pycryptodome beautifulsoup4 pyyaml
```

## 第二步：测试登录

运行测试脚本，验证登录逻辑是否正确：

```bash
python test_login.py
```

输入你的用户名和密码。如果登录成功，脚本会：
- ✅ 探索系统菜单
- ✅ 尝试常见的工时页面 URL
- ✅ 分析页面结构
- ✅ 保存找到的工时页面 HTML

## 第三步：分析实际系统

如果自动探测未找到工时页面，请手动分析：

### 方法 1：使用浏览器开发者工具

1. 打开浏览器（Chrome），访问 `http://10.111.36.3:2029`
2. 登录系统
3. 按 **F12** 打开开发者工具
4. 切换到 **Network** 标签
5. 手动填写一次工时
6. 查看提交时的请求：
   - 请求 URL（如 `/timesheet/submit.do`）
   - 请求方法（POST/GET）
   - 请求数据（Payload/Form Data）

### 方法 2：查看页面源代码

1. 在工时填写页面右键 → "查看网页源代码"
2. 查找表单的 `<form action="...">` 属性
3. 查找输入字段的 `name` 属性
4. 保存源代码到文件，用于分析

## 第四步：更新代码

根据探测结果，更新 `rdm_timesheet.py` 中的以下部分：

### 1. 工时页面 URL

```python
# 找到实际的工时录入页面 URL
url = f"{self.base_url}/timesheet/input.do"  # 替换为实际 URL
```

### 2. 获取任务列表

```python
def get_weekly_tasks(self, year=None, month=None):
    """根据实际 API 调整"""
    url = f"{self.base_url}/实际的任务API.do"
    params = {"year": year, "month": month}
    resp = self.session.get(url, params=params)
    return resp.json()
```

### 3. 提交工时

```python
def submit_timesheet(self, week_start, tasks):
    """根据实际数据格式调整"""
    url = f"{self.base_url}/实际的提交API.do"

    # 根据实际要求的格式构建数据
    data = {
        "weekStart": week_start,
        "tasks": [
            {
                "taskId": task["id"],
                "hours": task["hours"],
                "rate": task["completion_rate"]
            }
            for task in tasks
        ]
    }

    resp = self.session.post(url, json=data)
    return resp.json()
```

## 第五步：测试和使用

完成代码调整后：

```bash
python rdm_timesheet.py
```

按提示填写工时即可。

## 常见问题排查

### 登录失败

**原因**：密码加密逻辑可能不同

**解决**：
1. 打开浏览器 F12 → Network
2. 手动登录，查看 `/j_security_check` 请求的 Form Data
3. 对比 `j_username` 和 `j_password` 的值
4. 调整 `encrypt()` 函数

### 找不到工时页面

**原因**：系统使用 iframe 或动态加载

**解决**：
1. 检查 Network 标签中的所有请求
2. 查找包含 "工时" 关键词的 HTML 响应
3. 注意 iframe 的 src 属性

### 提交失败

**原因**：数据格式不匹配或缺少必填字段

**解决**：
1. 查看提交请求的完整 Form Data 或 Request Payload
2. 对比你的代码提交的数据
3. 添加缺失的字段（如 CSRF token、时间戳等）

## 需要帮助？

请提供以下信息：

1. **登录后的主页截图** - 显示菜单结构
2. **工时填写页面截图** - 显示字段布局
3. **Network 请求截图** - 特别是提交工时的请求
4. **页面源代码** - 右键 → 查看网页源代码，保存为文本文件

有了这些信息，可以快速完善工具。
