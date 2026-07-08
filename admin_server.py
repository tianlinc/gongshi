# -*- coding: utf-8 -*-
"""
License 签发管理端 — 独立程序，仅管理员本地使用

与客户应用（app.py）完全分离：
  - 运行在独立端口 5001
  - 不包含在客户打包/部署中
  - 仅管理员本地浏览器访问 http://localhost:5001

依赖：
  pip install flask flask-cors
  （与主项目共享 license_utils.py）

用法：
  python admin_server.py
  # 浏览器打开 http://localhost:5001
"""

from flask import Flask, render_template_string, request, jsonify
import os
import sys

# 确保能 import 项目根目录的 license_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from license_utils import generate_license, verify_license

admin_app = Flask(__name__)

# ===========================================================================
# 页面模板（内联 HTML，无需外部模板文件）
# ===========================================================================
PAGE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>License 签发工具</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        body { background: #f0f2f5; min-height: 100vh; }
        .tool-card { max-width: 560px; margin: 80px auto; }
        .tool-card .card {
            border: none; border-radius: 16px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.10);
        }
        .tool-card .card-header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff; border-radius: 16px 16px 0 0 !important;
            padding: 20px 24px;
        }
        .tool-card .card-header h5 { margin:0; font-weight:700; font-size:17px; }
        .tool-card .card-body { padding: 24px; }
        .result-box {
            background: #f0fdf4; border: 1px solid #bbf7d0;
            border-radius: 10px; padding: 16px; margin-top: 16px;
            display: none;
        }
        .result-box .license-text {
            font-family: 'Courier New', monospace; font-size: 12px;
            color: #166534; word-break: break-all;
            background: #fff; border: 1px solid #dcfce7;
            border-radius: 6px; padding: 10px 12px; margin: 8px 0;
        }
        .duration-options .btn-check:checked+.btn {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff; border-color: transparent;
        }
        .gen-btn {
            background: linear-gradient(135deg, #0d6efd 0%, #6610f2 100%);
            border: none; padding: 12px; font-size: 15px; font-weight: 600;
            border-radius: 10px; width: 100%; color: #fff;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .gen-btn:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(13,110,253,0.4); }
        .gen-btn:disabled { opacity: 0.65; transform: none; box-shadow: none; }
        .footer-note { text-align: center; color: #aaa; font-size: 12px; margin-top: 30px; }
    </style>
</head>
<body>
<div class="tool-card">
    <div class="card">
        <div class="card-header">
            <h5><i class="bi bi-key-fill"></i> License 签发工具</h5>
        </div>
        <div class="card-body">

            <div id="alertBox"></div>

            <div class="mb-3">
                <label for="snInput" class="form-label fw-bold">
                    <i class="bi bi-upc-scan"></i> 客户 SN 码
                </label>
                <textarea class="form-control" id="snInput" rows="2"
                    placeholder="粘贴客户提供的 SN 码"
                    style="font-family:'Courier New',monospace; font-size:13px;"></textarea>
            </div>

            <div class="mb-3">
                <label class="form-label fw-bold">
                    <i class="bi bi-calendar-range"></i> 授权时长
                </label>
                <div class="duration-options btn-group w-100" role="group">
                    <input type="radio" class="btn-check" name="duration" id="dur1y" value="1年" checked>
                    <label class="btn btn-outline-primary" for="dur1y">1 年</label>
                    <input type="radio" class="btn-check" name="duration" id="durForever" value="永久">
                    <label class="btn btn-outline-primary" for="durForever">永久</label>
                </div>
            </div>

            <button class="gen-btn" id="generateBtn">
                <span class="btn-text"><i class="bi bi-lightning-charge"></i> 生成 License</span>
                <span class="spinner-border spinner-border-sm" style="display:none;"></span>
            </button>

            <div class="result-box" id="resultBox">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <strong style="color:#166534;"><i class="bi bi-check-circle-fill"></i> 生成成功</strong>
                    <button class="btn btn-sm btn-outline-success" id="copyResultBtn">
                        <i class="bi bi-clipboard"></i> 复制
                    </button>
                </div>
                <div class="license-text" id="resultLicense"></div>
                <small class="text-muted">请将 License 字符串复制给客户</small>
            </div>

        </div>
    </div>
    <div class="footer-note">
        <i class="bi bi-shield-lock"></i> 仅管理员本地使用 &middot; 端口 5001
    </div>
</div>

<script>
(function () {
    const btn = document.getElementById('generateBtn');
    btn.addEventListener('click', async () => {
        const sn = document.getElementById('snInput').value.trim();
        if (!sn) { showAlert('danger','请输入客户 SN 码'); return; }
        const dur = document.querySelector('input[name="duration"]:checked').value;
        btn.querySelector('.btn-text').style.display = 'none';
        btn.querySelector('.spinner-border').style.display = 'inline-block';
        btn.disabled = true;
        document.getElementById('resultBox').style.display = 'none';
        document.getElementById('alertBox').innerHTML = '';
        try {
            const r = await fetch('/api/generate', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({sn:sn, duration:dur})
            });
            const d = await r.json();
            if (d.success) {
                document.getElementById('resultLicense').textContent = d.license;
                document.getElementById('resultBox').style.display = 'block';
            } else {
                showAlert('danger', d.message || '生成失败');
            }
        } catch(e) {
            showAlert('danger', '网络错误，请重试');
        } finally {
            btn.querySelector('.btn-text').style.display = '';
            btn.querySelector('.spinner-border').style.display = 'none';
            btn.disabled = false;
        }
    });
    document.getElementById('copyResultBtn').addEventListener('click', async () => {
        const lic = document.getElementById('resultLicense').textContent.trim();
        if (!lic) return;
        try { await navigator.clipboard.writeText(lic); } catch(e) {
            const ta = document.createElement('textarea'); ta.value = lic;
            ta.style.position='fixed'; ta.style.left='-9999px';
            document.body.appendChild(ta); ta.select();
            document.execCommand('copy'); document.body.removeChild(ta);
        }
        const cb = document.getElementById('copyResultBtn');
        const orig = cb.innerHTML;
        cb.innerHTML = '<i class="bi bi-check"></i> 已复制';
        cb.classList.add('btn-success'); cb.classList.remove('btn-outline-success');
        setTimeout(() => { cb.innerHTML=orig; cb.classList.remove('btn-success'); cb.classList.add('btn-outline-success'); }, 2000);
    });
    function showAlert(type, msg) {
        const box = document.getElementById('alertBox');
        const m = {danger:'danger',success:'success',warning:'warning'};
        box.className = 'alert alert-'+(m[type]||'info');
        box.textContent = msg;
    }
})();
</script>
</body>
</html>"""


# ===========================================================================
# 路由
# ===========================================================================

@admin_app.route('/')
def index():
    """License 签发页面"""
    return render_template_string(PAGE_HTML)


@admin_app.route('/api/generate', methods=['POST'])
def api_generate():
    """
    生成 License。

    请求：{ "sn": "...", "duration": "1年" | "永久" }
    响应：{ "success": true, "license": "..." }
    """
    data = request.get_json(silent=True) or {}
    sn = (data.get('sn') or '').strip()
    duration = (data.get('duration') or '').strip()

    if not sn:
        return jsonify({'success': False, 'message': '请输入 SN 码'})
    if duration not in ('1年', '永久'):
        return jsonify({'success': False, 'message': "时长类型必须为 '1年' 或 '永久'"})

    try:
        license_str = generate_license(sn, duration)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})

    # 自验证
    valid, _, err = verify_license(license_str)
    if not valid:
        print(f"[X] 自验证失败: {err}")
        return jsonify({'success': False, 'message': f'自验证失败: {err}'})

    print(f"[OK] License 生成 sn={sn[:20]}... duration={duration}")
    return jsonify({
        'success': True,
        'license': license_str,
        'sn': sn,
        'duration': duration,
    })


# ===========================================================================
# 入口
# ===========================================================================

if __name__ == '__main__':
    print("=" * 50)
    print("  License 签发管理端")
    print("=" * 50)
    print()
    print("  浏览器访问: http://localhost:5001")
    print("  按 Ctrl+C 停止")
    print()
    print("  此程序仅管理员本地使用，不提供给客户。")
    print("=" * 50)

    admin_app.run(debug=True, host='127.0.0.1', port=5001)
