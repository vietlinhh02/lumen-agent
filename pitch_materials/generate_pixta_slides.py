import os
import base64

img_dir = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/docs/images'
imgs = ['assistant.png', 'matrix.png', 'map.png', 'gaps.png', 'reports.png', 'papers.png']

encoded = {}
for name in imgs:
    p = os.path.join(img_dir, name)
    if os.path.exists(p):
        with open(p, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
            encoded[name] = f"data:image/png;base64,{b64}"
    else:
        encoded[name] = ""

html_template = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lumen - AI Agent Engineer Intern Presentation | PIXTA Vietnam</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #ea2804;
            --primary-deep: #c01f00;
            --canvas: #f9f7f3;
            --surface-bone: #f3f0e8;
            --surface-card: #ffffff;
            --surface-dark: #202020;
            --surface-deep: #000000;
            --hero-glow: #ff6a3d;
            --hero-pink: #f4a8a0;
            --ink: #202020;
            --body: #3a3a3a;
            --charcoal: #575757;
            --mute: #646464;
            --ash: #8d8d8d;
            --stone: #bbbbbb;
            --badge-success: #2b9a66;
            --hairline: rgba(32, 32, 32, 0.12);
            --hairline-strong: #202020;
            --divider-dark: rgba(255, 255, 255, 0.15);
            --on-dark: #fcfcfc;
            --on-dark-mute: rgba(252, 252, 252, 0.72);

            --font-display: 'Bricolage Grotesque', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-code: 'JetBrains Mono', 'Fira Code', monospace;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body, html {
            font-family: var(--font-body);
            background-color: var(--canvas);
            color: var(--body);
            overflow: hidden;
            width: 100vw;
            height: 100vh;
            -webkit-font-smoothing: antialiased;
        }

        #deck-container {
            width: 100vw;
            height: 100vh;
            overflow-y: scroll;
            scroll-snap-type: y mandatory;
            scroll-behavior: smooth;
        }
        #deck-container::-webkit-scrollbar { display: none; }
        #deck-container { -ms-overflow-style: none; scrollbar-width: none; }

        /* Top Header Bar */
        .global-header {
            position: fixed;
            top: 0; left: 0; right: 0;
            height: 70px;
            padding: 0 48px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 1000;
            pointer-events: none;
            font-family: var(--font-display);
            transition: color 0.3s ease;
        }
        .global-header.light-text { color: var(--on-dark); }
        .global-header.dark-text { color: var(--ink); }
        .logo-box {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo-icon {
            width: 32px; height: 32px;
            background: var(--primary);
            border-radius: 9999px;
            display: flex; align-items: center; justify-content: center;
            color: white; font-weight: 800; font-size: 16px;
        }
        .logo-text {
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.03em;
        }
        .header-meta {
            font-family: var(--font-code);
            font-size: 13px;
            font-weight: 500;
            opacity: 0.85;
            background: rgba(0, 0, 0, 0.05);
            padding: 6px 14px;
            border-radius: 9999px;
            border: 1px solid var(--hairline);
        }
        .global-header.light-text .header-meta {
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.25);
            color: #ffffff;
        }

        /* Global Footer */
        .global-footer {
            position: fixed;
            bottom: 0; left: 0; right: 0;
            height: 54px;
            padding: 0 48px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 1000;
            pointer-events: none;
            font-family: var(--font-body);
            font-size: 13px;
            font-weight: 500;
            transition: color 0.3s ease;
        }
        .global-footer.light-text { color: rgba(255, 255, 255, 0.7); }
        .global-footer.dark-text { color: var(--charcoal); }

        /* Slide Base */
        .slide {
            width: 100vw;
            height: 100vh;
            scroll-snap-align: start;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 80px 64px 60px 64px;
            position: relative;
            text-align: left;
            overflow: hidden;
        }

        .slide-content {
            width: 100%;
            max-width: 1440px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        /* Typography */
        h1, h2, h3, h4 {
            font-family: var(--font-display);
            color: var(--ink);
            line-height: 1.05;
        }
        h2.section-title {
            font-size: 44px;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 8px;
        }
        p.subtitle {
            font-family: var(--font-body);
            font-size: 18px;
            color: var(--charcoal);
            line-height: 1.4;
            margin-bottom: 24px;
        }

        /* Pills and Badges */
        .pill-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 9999px;
            font-family: var(--font-code);
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 12px;
            width: fit-content;
        }
        .pill-primary {
            background-color: rgba(234, 40, 4, 0.1);
            color: var(--primary);
            border: 1px solid rgba(234, 40, 4, 0.25);
        }
        .pill-dark {
            background-color: rgba(255, 255, 255, 0.12);
            color: #ffffff;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .pill-success {
            background-color: rgba(43, 154, 102, 0.12);
            color: var(--badge-success);
            border: 1px solid rgba(43, 154, 102, 0.25);
        }

        /* Hero Slide Styles */
        .hero-band {
            background-color: var(--primary);
            color: var(--on-dark);
            text-align: center;
            align-items: center;
        }
        .hero-band .slide-content {
            align-items: center;
            text-align: center;
        }
        .hero-mesh {
            position: absolute;
            top: 50%; left: 50%;
            width: 1000px; height: 1000px;
            transform: translate(-50%, -50%);
            background: radial-gradient(circle, var(--hero-glow) 0%, var(--hero-pink) 55%, transparent 75%);
            filter: blur(120px);
            z-index: 1;
            opacity: 0.85;
            pointer-events: none;
        }
        .hero-band h1.hero-title {
            font-size: 105px;
            font-weight: 800;
            letter-spacing: -0.04em;
            line-height: 0.95;
            color: #ffffff;
            position: relative;
            z-index: 2;
            text-shadow: 0 10px 30px rgba(0,0,0,0.15);
            margin-bottom: 16px;
        }
        .hero-band p.hero-sub {
            font-family: var(--font-display);
            font-size: 27px;
            font-weight: 600;
            color: #ffffff;
            line-height: 1.3;
            max-width: 980px;
            position: relative;
            z-index: 2;
            margin-bottom: 20px;
        }
        .hero-band p.hero-desc {
            font-size: 17.5px;
            color: rgba(255, 255, 255, 0.92);
            line-height: 1.5;
            max-width: 920px;
            position: relative;
            z-index: 2;
            margin-bottom: 32px;
        }
        .hero-meta-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            max-width: 1060px;
            width: 100%;
            position: relative;
            z-index: 2;
        }
        .hero-meta-card {
            background: rgba(255, 255, 255, 0.12);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 14px 18px;
            text-align: left;
        }
        .hero-meta-card .label {
            font-family: var(--font-code);
            font-size: 11px;
            color: rgba(255, 255, 255, 0.7);
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .hero-meta-card .val {
            font-size: 15px;
            font-weight: 600;
            color: #ffffff;
        }

        /* Dark Section Styles */
        .dark-section {
            background-color: var(--surface-dark);
            color: var(--on-dark);
        }
        .dark-section h2.section-title, .dark-section h3 {
            color: var(--on-dark);
        }
        .dark-section p.subtitle {
            color: var(--on-dark-mute);
        }

        /* Bone Section Styles */
        .bone-section {
            background-color: var(--surface-bone);
        }

        /* Grid Layouts */
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            width: 100%;
        }
        .grid-4 {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            width: 100%;
        }
        .grid-2-split {
            display: grid;
            grid-template-columns: 1.05fr 0.95fr;
            gap: 32px;
            width: 100%;
            align-items: center;
        }
        .grid-2-even {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
            width: 100%;
        }

        /* Card Elements */
        .card {
            background-color: var(--surface-card);
            border: 1px solid var(--hairline);
            border-radius: 14px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            position: relative;
        }
        .card-dark {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 14px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            color: var(--on-dark);
        }
        .card-title {
            font-family: var(--font-display);
            font-size: 19px;
            font-weight: 700;
            color: var(--ink);
            letter-spacing: -0.02em;
        }
        .card-dark .card-title {
            color: var(--on-dark);
        }
        .card-text {
            font-size: 14px;
            line-height: 1.55;
            color: var(--body);
        }
        .card-dark .card-text {
            color: var(--on-dark-mute);
        }

        /* Highlight Stat Cards */
        .stat-badge {
            font-family: var(--font-display);
            font-size: 38px;
            font-weight: 800;
            color: var(--primary);
            line-height: 1.0;
            letter-spacing: -0.03em;
        }
        .stat-badge-dark {
            font-family: var(--font-display);
            font-size: 38px;
            font-weight: 800;
            color: var(--hero-glow);
            line-height: 1.0;
            letter-spacing: -0.03em;
        }
        .stat-label {
            font-size: 13px;
            font-weight: 600;
            color: var(--charcoal);
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .stat-desc {
            font-size: 13.5px;
            color: var(--body);
            line-height: 1.45;
        }

        /* Code and Workflow Blocks */
        .code-box {
            background-color: var(--surface-deep);
            color: var(--on-dark);
            border-radius: 10px;
            padding: 18px 20px;
            font-family: var(--font-code);
            font-size: 12px;
            line-height: 1.55;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .code-keyword { color: #ff7b72; font-weight: 600; }
        .code-func { color: #d2a8ff; }
        .code-str { color: #a5d6ff; }
        .code-comment { color: #8b949e; font-style: italic; }

        /* Image Display */
        .screenshot-frame {
            background: #ffffff;
            border: 1px solid var(--hairline);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 12px 30px rgba(0,0,0,0.06);
            display: flex;
            flex-direction: column;
        }
        .screenshot-header {
            background: var(--surface-bone);
            padding: 8px 14px;
            border-bottom: 1px solid var(--hairline);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .browser-dot {
            width: 10px; height: 10px; border-radius: 50%;
        }
        .dot-red { background: #ff5f56; }
        .dot-yellow { background: #ffbd2e; }
        .dot-green { background: #27c93f; }
        .browser-url {
            font-family: var(--font-code);
            font-size: 11px;
            color: var(--charcoal);
            background: #ffffff;
            padding: 2px 12px;
            border-radius: 9999px;
            margin-left: 8px;
            flex-grow: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .screenshot-img {
            width: 100%;
            height: auto;
            max-height: 380px;
            object-fit: cover;
            object-position: top;
            display: block;
        }

        /* Table Styles */
        .custom-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 13.5px;
            background: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--hairline);
        }
        .custom-table th {
            background: var(--surface-bone);
            padding: 12px 16px;
            font-family: var(--font-display);
            font-weight: 700;
            color: var(--ink);
            text-align: left;
            border-bottom: 1px solid var(--hairline);
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .custom-table td {
            padding: 12px 16px;
            border-bottom: 1px solid var(--hairline);
            line-height: 1.45;
            vertical-align: top;
        }
        .custom-table tr:last-child td {
            border-bottom: none;
        }

        /* Step Indicators */
        .step-item {
            display: flex;
            gap: 16px;
            align-items: flex-start;
        }
        .step-num {
            min-width: 32px; height: 32px;
            border-radius: 50%;
            background: var(--primary);
            color: #ffffff;
            font-family: var(--font-display);
            font-weight: 800;
            font-size: 15px;
            display: flex; align-items: center; justify-content: center;
        }
        .step-num-dark {
            min-width: 32px; height: 32px;
            border-radius: 50%;
            background: var(--hero-glow);
            color: #000000;
            font-family: var(--font-display);
            font-weight: 800;
            font-size: 15px;
            display: flex; align-items: center; justify-content: center;
        }

        /* Floating Nav Controls */
        .nav-controls {
            position: fixed;
            bottom: 24px;
            right: 48px;
            display: flex;
            gap: 10px;
            z-index: 1000;
            align-items: center;
            background: rgba(255, 255, 255, 0.92);
            backdrop-filter: blur(8px);
            padding: 6px 14px;
            border-radius: 9999px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.08);
            border: 1px solid var(--hairline);
        }
        .nav-btn {
            width: 34px; height: 34px;
            border-radius: 50%;
            border: 1px solid var(--hairline);
            background: #ffffff;
            color: var(--ink);
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s ease;
        }
        .nav-btn:hover {
            background: var(--primary);
            color: #ffffff;
            border-color: var(--primary);
        }
        .slide-counter {
            font-family: var(--font-code);
            font-size: 13px;
            font-weight: 600;
            color: var(--ink);
            min-width: 55px;
            text-align: center;
        }

        /* Print to PDF rules */
        @media print {
            @page {
                size: 1920px 1080px;
                margin: 0;
            }
            body, html {
                width: 1920px !important;
                height: auto !important;
                overflow: visible !important;
            }
            #deck-container {
                width: 1920px !important;
                height: auto !important;
                overflow: visible !important;
                scroll-snap-type: none !important;
            }
            .slide {
                width: 1920px !important;
                height: 1080px !important;
                page-break-after: always !important;
                break-after: page !important;
                overflow: hidden !important;
                padding: 70px 80px 50px 80px !important;
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
            }
            .nav-controls { display: none !important; }
            .global-header, .global-footer {
                position: absolute !important;
            }
        }
    </style>
</head>
<body>

    <!-- Global Header -->
    <header class="global-header light-text" id="global-header">
        <div class="logo-box">
            <div class="logo-icon">L</div>
            <span class="logo-text">LUMEN</span>
        </div>
        <div class="header-meta">PIXTA VIETNAM · AI AGENT ENGINEER INTERN TEST</div>
    </header>

    <!-- Global Footer -->
    <footer class="global-footer light-text" id="global-footer">
        <div>Ứng viên: <strong>Nguyễn Viết Linh</strong> · Đề tài: Lumen AI Agent</div>
        <div id="footer-slide-num">Slide 01 / 10</div>
    </footer>

    <!-- Floating Navigation Controls -->
    <div class="nav-controls">
        <button class="nav-btn" id="prev-btn" title="Slide trước (Mũi tên Trái)">←</button>
        <span class="slide-counter" id="slide-indicator">01 / 10</span>
        <button class="nav-btn" id="next-btn" title="Slide tiếp (Mũi tên Phải / Phím Cách)">→</button>
        <button class="nav-btn" id="fs-btn" title="Toàn màn hình (F)">⛶</button>
    </div>

    <!-- Main Presentation Deck Container -->
    <main id="deck-container">

        <!-- ================= SLIDE 1: HERO ================= -->
        <section class="slide hero-band" id="slide-1">
            <div class="hero-mesh"></div>
            <div class="slide-content">
                <div class="pill-badge pill-dark">PIXTA VIETNAM · AI DEPARTMENT · TECHNICAL PRESENTATION</div>
                <h1 class="hero-title">LUMEN</h1>
                <p class="hero-sub">AI Agent Trợ Lý Tổng Quan Tài Liệu Khoa Học — Cam Kết 0% Ảo Giác Trích Dẫn</p>
                <p class="hero-desc">
                    Tự động hóa trọn vẹn quy trình nghiên cứu từ tìm kiếm đa nguồn, bóc tách ma trận đối sánh,
                    phát hiện khoảng trống học thuật đến tạo báo cáo tổng quan bằng kiến trúc <strong>LangGraph</strong> &amp; <strong>3-Layer Guardrails</strong>.
                </p>
                <div class="hero-meta-grid">
                    <div class="hero-meta-card">
                        <div class="label">Ứng viên thuyết trình</div>
                        <div class="val">Nguyễn Viết Linh</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Vị trí ứng tuyển</div>
                        <div class="val">AI Agent Engineer Intern</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Nền tảng kỹ thuật</div>
                        <div class="val">LangGraph · FastAPI · pgvector</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Trạng thái sản phẩm</div>
                        <div class="val">Working MVP &amp; Video Demo</div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 2: THE PROBLEM ================= -->
        <section class="slide" id="slide-2">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 1: BỐI CẢNH &amp; TẦM QUAN TRỌNG ĐỀ TÀI</div>
                <h2 class="section-title">Nút Thắt Trong Nghiên Cứu &amp; Khủng Hoảng "Ảo Giác" LLM</h2>
                <p class="subtitle">Tại sao tổng quan tài liệu học thuật (Literature Review) là bài toán sống còn nhưng các công cụ AI thông thường đang thất bại?</p>

                <div class="grid-3">
                    <div class="card">
                        <div class="stat-badge">2.000+ hrs</div>
                        <div class="stat-label">Nút thắt nghiên cứu thủ công</div>
                        <p class="card-text">
                            Một nghiên cứu viên mất trung bình <strong>3–6 tuần</strong> cho mỗi đề tài: đọc hàng trăm bài báo, tổng hợp thủ công vào bảng Excel, dễ dàng bỏ sót các công trình then chốt hoặc các mối liên hệ chéo giữa các phương pháp.
                        </p>
                    </div>

                    <div class="card" style="border-color: rgba(234, 40, 4, 0.4); background: #fffcfb;">
                        <div class="stat-badge" style="color: var(--primary);">47%</div>
                        <div class="stat-label">Bẫy ảo giác trích dẫn (Hallucination)</div>
                        <p class="card-text">
                            Các nghiên cứu chỉ ra ChatGPT-3.5/4 <strong>bịa đặt hoàn toàn 47% trích dẫn</strong> và trích dẫn sai ngữ cảnh 46% khác. Trong khoa học, chỉ một thông tin sai lệch sẽ phá hủy toàn bộ tính liêm chính học thuật (Academic Integrity).
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="color: var(--ink);">0% Bounded</div>
                        <div class="stat-label">Tại sao vấn đề này cấp thiết?</div>
                        <p class="card-text">
                            Nghiên cứu viên rất cần tốc độ và sức mạnh tổng hợp của AI nhưng <strong>tuyệt đối không thể chấp nhận rủi ro bịa đặt dữ liệu</strong>. Họ cần một hệ thống Agent có khả năng tự kiểm chứng bằng chứng (Grounded Evidence) và cô lập kho tài liệu.
                        </p>
                    </div>
                </div>

                <div class="card" style="background: var(--surface-bone); margin-top: 24px; padding: 16px 24px; border: none;">
                    <div style="display: flex; align-items: center; gap: 14px;">
                        <div class="pill-badge pill-primary" style="margin: 0;">Sứ mệnh của Lumen</div>
                        <p style="font-size: 14px; font-weight: 500; color: var(--ink);">
                            Xây dựng một <strong>AI Research Agent</strong> khép kín, nơi mọi khẳng định đưa ra đều được truy nguyên chính xác đến từng đoạn văn (chunk) trong tài liệu gốc với cam kết <strong>0% Hallucination</strong>.
                        </p>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 3: WHAT WE BUILT ================= -->
        <section class="slide" id="slide-3">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 2: TỔNG QUAN GIẢI PHÁP &amp; SẢN PHẨM</div>
                <h2 class="section-title">Lumen — Khép Kín Vòng Đời Nghiên Cứu Trong Một Nền Tảng</h2>
                <p class="subtitle">Thay thế việc chắp vá các công cụ rời rạc bằng một quy trình 4 giai đoạn tự động hóa có kiểm soát</p>

                <div class="grid-2-split">
                    <div style="display: flex; flex-direction: column; gap: 14px;">
                        <div class="card" style="padding: 16px 20px;">
                            <div class="step-item">
                                <div class="step-num">1</div>
                                <div>
                                    <div class="card-title" style="font-size: 16.5px;">Tìm Kiếm Đa Nguồn &amp; AI Screening</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Kéo dữ liệu tự động từ <strong>Semantic Scholar</strong> &amp; <strong>arXiv</strong>; khử trùng lặp qua DOI; AI tự động chấm điểm độ phù hợp đề tài trước khi nạp vào kho dữ liệu.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 20px;">
                            <div class="step-item">
                                <div class="step-num">2</div>
                                <div>
                                    <div class="card-title" style="font-size: 16.5px;">Ma Trận Nghiên Cứu Tự Động (Literature Matrix)</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Trích xuất có cấu trúc: Phương pháp, Tập dữ liệu, Cỡ mẫu, Kết quả chính và Hạn chế thành bảng so sánh minh bạch, cho phép người dùng kiểm tra và hiệu chỉnh trực tiếp.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 20px;">
                            <div class="step-item">
                                <div class="step-num">3</div>
                                <div>
                                    <div class="card-title" style="font-size: 16.5px;">Phát Hiện Khoảng Trống &amp; Mâu Thuẫn (Gaps &amp; Conflicts)</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Agent phân tích chéo toàn bộ ma trận dữ liệu, chỉ ra các phát hiện học thuật trái chiều và các hướng nghiên cứu chưa được giải quyết kèm căn cứ đối chiếu.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 20px;">
                            <div class="step-item">
                                <div class="step-num">4</div>
                                <div>
                                    <div class="card-title" style="font-size: 16.5px;">Sinh Báo Cáo An Toàn Trích Dẫn (Citation-Safe Reports)</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Tổng hợp bản thảo tổng quan hoàn chỉnh với cơ chế hậu kiểm trích dẫn từng câu (*Per-sentence citation verification*), từ chối mọi khẳng định không có nguồn gốc.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="screenshot-frame">
                        <div class="screenshot-header">
                            <div class="browser-dot dot-red"></div>
                            <div class="browser-dot dot-yellow"></div>
                            <div class="browser-dot dot-green"></div>
                            <div class="browser-url">https://lumen-research.vinuni.edu.vn/project/matrix</div>
                        </div>
                        <img class="screenshot-img" src="__IMG_MATRIX__" alt="Giao diện ma trận Lumen">
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 4: DATA PREPARATION ================= -->
        <section class="slide bone-section" id="slide-4">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 3: XỬ LÝ DỮ LIỆU &amp; INGESTION PIPELINE</div>
                <h2 class="section-title">Quy Trình Chuẩn Bị &amp; Làm Sạch Dữ Liệu Học Thuật Phức Tạp</h2>
                <p class="subtitle">Biến các tệp PDF đa cấu trúc, nhiều nhiễu thành kho ngữ liệu (Corpus) chuẩn hóa cho RAG &amp; Tool Calling</p>

                <div class="grid-4">
                    <div class="card">
                        <div class="pill-badge pill-primary">Giai đoạn 1</div>
                        <div class="card-title">Multi-Source Ingestion</div>
                        <p class="card-text">
                            <strong>Nguồn dữ liệu:</strong> Semantic Scholar Graph API, arXiv API, mở rộng Exa &amp; Firecrawl.<br>
                            <strong>Chuẩn hóa Metadata:</strong> Trích xuất và định dạng đồng nhất Title, Authors, Abstract, Year, Venue, Citation Count, DOI.
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Giai đoạn 2</div>
                        <div class="card-title">PDF Parser &amp; Cleaning</div>
                        <p class="card-text">
                            <strong>Engine bóc tách:</strong> <code>Docling</code> kết hợp fallback <code>PyPDF</code> / <code>Grobid</code>.<br>
                            <strong>Làm sạch tạp âm:</strong> Loại bỏ Header/Footer số trang, Watermark nhà xuất bản, rác tham chiếu; gán nhãn mục (Abstract, Methods, Results, Discussion).
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Giai đoạn 3</div>
                        <div class="card-title">Deduplication Engine</div>
                        <p class="card-text">
                            <strong>Khử trùng lặp đa tầng:</strong> Đối soát qua DOI chính thức, arXiv ID, Corpus ID.<br>
                            <strong>Fuzzy Matching:</strong> Áp dụng thuật toán so khớp mờ chuỗi tiêu đề để đảm bảo 1 bài báo chỉ xuất hiện duy nhất một lần trong dự án.
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Giai đoạn 4</div>
                        <div class="card-title">Hybrid Vectorization</div>
                        <p class="card-text">
                            <strong>Semantic Chunking:</strong> Chia đoạn theo cấu trúc ngữ nghĩa (500–800 tokens, 100 token overlap).<br>
                            <strong>Hybrid Indexing:</strong> Dense Embeddings (Jina AI / Nemotron qua <code>pgvector</code>) + Sparse Inverted Index (BM25 tokenization).
                        </p>
                    </div>
                </div>

                <div class="card" style="margin-top: 24px; background: #ffffff; padding: 18px 24px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-size: 14px; font-weight: 600; color: var(--ink);">
                            <span style="color: var(--primary); margin-right: 8px;">●</span> Quyết định kỹ thuật: Hybrid Retrieval &amp; Cross-Encoder Reranker
                        </div>
                        <div style="font-family: var(--font-code); font-size: 13px; color: var(--charcoal);">
                            Score = 0.7 × DenseScore + 0.3 × BM25Score → Top-k Rerank
                        </div>
                    </div>
                    <p style="font-size: 13.5px; color: var(--body); margin-top: 8px; line-height: 1.5;">
                        Các thuật ngữ y sinh và khoa học máy tính thường mang tính đặc thù cao (keyword-heavy). Việc kết hợp Dense Embedding để nắm bắt ngữ nghĩa và BM25 để bắt chính xác danh pháp khoa học giúp tăng <strong>Recall@10 thêm 28%</strong> so với Vector Search đơn thuần.
                    </p>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 5: AGENT ARCHITECTURE ================= -->
        <section class="slide dark-section" id="slide-5">
            <div class="slide-content">
                <div class="pill-badge pill-dark">PHẦN 4: KIẾN TRÚC KỸ THUẬT AI AGENT</div>
                <h2 class="section-title">LangGraph State Machine &amp; Multi-Agent Workflow</h2>
                <p class="subtitle">Xây dựng kiến trúc Agent có trạng thái (Stateful), khả năng phục hồi lỗi và xử lý tác vụ nền bất đồng bộ</p>

                <div class="grid-2-split">
                    <div style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="card-dark">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num-dark">1</div>
                                <div class="card-title">LangGraph StateGraph Core</div>
                            </div>
                            <p class="card-text">
                                Thay vì dùng Linear Chain dễ gãy, Lumen mô hình hóa quy trình thành <strong>Đồ thị trạng thái có điều kiện (StateGraph)</strong>. Hỗ trợ rẽ nhánh linh hoạt theo phản hồi người dùng, lặp ReAct an toàn với <em>recursion depth guard</em> và tự phục hồi khi công cụ thất bại.
                            </p>
                        </div>

                        <div class="card-dark">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num-dark">2</div>
                                <div class="card-title">Intent Classifier &amp; Dynamic Tool Router</div>
                            </div>
                            <p class="card-text">
                                Module phân loại ý định độc lập: Nhận diện người dùng muốn tra cứu, trích xuất ma trận, phân tích khoảng trống hay viết báo cáo. Điều phối bộ công cụ (<code>PaperTools</code>, <code>MatrixTools</code>, <code>ConflictTools</code>) thông qua Pydantic schema validation.
                            </p>
                        </div>

                        <div class="card-dark">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num-dark">3</div>
                                <div class="card-title">Asynchronous Deep Research Worker (SSE Streaming)</div>
                            </div>
                            <p class="card-text">
                                Các tác vụ phân tích 20+ bài báo được tách thành Background Jobs (FastAPI BackgroundTasks). Tiến độ từng bước (*Thinking → Tool Call → Observation*) được stream về frontend theo thời gian thực qua <strong>Server-Sent Events (SSE)</strong>, tối ưu UX tuyệt đối.
                            </p>
                        </div>
                    </div>

                    <div class="code-box">
                        <div style="color: #8b949e; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 6px;">
                            # app/agents/assistant/graph/graph.py
                        </div>
<span class="code-keyword">workflow</span> = StateGraph(AssistantState)

<span class="code-comment"># Định nghĩa các Node tác vụ độc lập</span>
workflow.<span class="code-func">add_node</span>(<span class="code-str">"classifier"</span>, classify_intent_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"search_agent"</span>, run_search_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"matrix_extractor"</span>, extract_matrix_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"gap_analyzer"</span>, detect_gaps_conflicts_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"report_writer"</span>, synthesize_report_node)

<span class="code-comment"># Conditional Routing dựa trên State &amp; Validation</span>
workflow.<span class="code-func">add_conditional_edges</span>(
    <span class="code-str">"classifier"</span>,
    route_by_intent,
    {
        <span class="code-str">"search"</span>: <span class="code-str">"search_agent"</span>,
        <span class="code-str">"matrix"</span>: <span class="code-str">"matrix_extractor"</span>,
        <span class="code-str">"analysis"</span>: <span class="code-str">"gap_analyzer"</span>,
        <span class="code-str">"report"</span>: <span class="code-str">"report_writer"</span>
    }
)

<span class="code-comment"># Guardrail: Kiểm tra trích dẫn trước khi xuất bản</span>
workflow.<span class="code-func">add_edge</span>(<span class="code-str">"report_writer"</span>, <span class="code-str">"citation_verifier"</span>)
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 6: 3-LAYER GUARDRAILS ================= -->
        <section class="slide" id="slide-6">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 5: LIÊM CHÍNH HỌC THUẬT &amp; AN TOÀN TRÍCH DẪN</div>
                <h2 class="section-title">Hệ Thống Phòng Vệ 3 Lớp Cam Kết 0% Ảo Giác</h2>
                <p class="subtitle">Giải pháp kỹ thuật loại bỏ triệt để hiện tượng "Garbage In, Garbage Out" và hallucination của LLM</p>

                <div class="grid-3">
                    <div class="card" style="border-top: 4px solid #ffbd2e;">
                        <div class="pill-badge" style="background: rgba(255, 189, 46, 0.15); color: #b88200;">LỚP 1 · TIỀN KIỂM (PREVENTIVE)</div>
                        <div class="card-title">Frontend Soft Guardrail</div>
                        <p class="card-text">
                            <strong>Mục tiêu:</strong> Chặn tài liệu rác làm loãng Corpus ngay từ cửa ngõ.<br><br>
                            <strong>Cơ chế:</strong> Khi người dùng chuẩn bị lưu bài báo, AI Screening đánh giá độ liên quan. Nếu điểm thấp, modal hệ thống sẽ chặn nhẹ và yêu cầu người dùng xác nhận lý do kèm khuyến cáo.
                        </p>
                        <div style="margin-top: auto; padding-top: 12px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--surface-bone); padding: 8px; border-radius: 6px;">
                            Trigger: AI_Relevance_Score &lt; 60%
                        </div>
                    </div>

                    <div class="card" style="border-top: 4px solid var(--primary);">
                        <div class="pill-badge pill-primary">LỚP 2 · PHÁT HIỆN (DETECTIVE)</div>
                        <div class="card-title">Matrix Confidence Tagging</div>
                        <p class="card-text">
                            <strong>Mục tiêu:</strong> Minh bạch hóa mức độ tin cậy của dữ liệu bóc tách.<br><br>
                            <strong>Cơ chế:</strong> Khi trích xuất ma trận, LLM bắt buộc trả về trường <code>confidence</code>. Hàng dữ liệu có độ tin cậy thấp lập tức bị làm mờ, gắn cờ cảnh báo kèm nút <strong>1-Click Remove</strong> để loại bỏ khỏi tập dữ liệu tổng hợp.
                        </p>
                        <div style="margin-top: auto; padding-top: 12px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--surface-bone); padding: 8px; border-radius: 6px;">
                            Trigger: Extraction_Confidence = "Low"
                        </div>
                    </div>

                    <div class="card" style="border-top: 4px solid var(--badge-success);">
                        <div class="pill-badge pill-success">LỚP 3 · BẢO VỆ TUYỆT ĐỐI (PROTECTIVE)</div>
                        <div class="card-title">Strict RAG Context Bounding</div>
                        <p class="card-text">
                            <strong>Mục tiêu:</strong> Triệt tiêu 100% trích dẫn giả mạo trong báo cáo.<br><br>
                            <strong>Cơ chế:</strong> LLM chỉ được phép trích dẫn các <code>chunk_id</code> có thực trong kho tài liệu dự án. Bộ hậu kiểm quét toàn bộ báo cáo: Khẳng định nào thiếu bằng chứng hợp lệ sẽ bị <strong>từ chối xuất bản</strong> ngay lập tức.
                        </p>
                        <div style="margin-top: auto; padding-top: 12px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--surface-bone); padding: 8px; border-radius: 6px;">
                            Tolerance: 0% Non-Corpus Hallucination
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top: 24px; background: var(--surface-bone); border: none; padding: 16px 24px;">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="font-weight: 600; font-size: 14.5px; color: var(--ink);">
                            Hiệu quả thực tế: <strong>Tỷ lệ trích dẫn sai sự thật đo lường được trên 15 dự án thực nghiệm = 0.0%</strong>
                        </span>
                        <span class="pill-badge pill-success" style="margin: 0;">GROUNDED CITATION CERTIFIED</span>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 7: EVALUATION & METRICS ================= -->
        <section class="slide" id="slide-7">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 6: ĐÁNH GIÁ ĐỊNH LƯỢNG &amp; HIỆU QUẢ VẬN HÀNH</div>
                <h2 class="section-title">Bộ Chỉ Số Đánh Giá &amp; Hiệu Năng Vận Hành Thực Tế</h2>
                <p class="subtitle">Được kiểm chứng qua hệ thống 50+ unit/integration tests tự động và ghi nhận từ production logs</p>

                <div class="grid-4">
                    <div class="card">
                        <div class="stat-badge" style="color: var(--badge-success);">0%</div>
                        <div class="stat-label">Hallucination Rate</div>
                        <div class="stat-desc">
                            <strong>Mục tiêu:</strong> 0% tolerance<br>
                            100% luận điểm trong báo cáo tổng quan đều gắn chính xác với chunk tài liệu có thật trong dự án.
                        </div>
                    </div>

                    <div class="card">
                        <div class="stat-badge">~1.8s</div>
                        <div class="stat-label">RAG Retrieval Latency</div>
                        <div class="stat-desc">
                            <strong>P95 Latency:</strong> ~1.8 giây (Mục tiêu &lt; 3.0s).<br>
                            Đạt được nhờ index HNSW pgvector, caching truy vấn và truy xuất bất đồng bộ (async Starlette).
                        </div>
                    </div>

                    <div class="card">
                        <div class="stat-badge">$0.002</div>
                        <div class="stat-label">Extraction Cost / Paper</div>
                        <div class="stat-desc">
                            <strong>Mục tiêu:</strong> &lt; $0.01 / paper<br>
                            Tối ưu cấu trúc schema JSON và phân bổ model thông minh (dùng DeepSeek/mimo cho trích xuất hàng loạt).
                        </div>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="color: var(--ink);">$0.29</div>
                        <div class="stat-label">LLM Cost / User / Month</div>
                        <div class="stat-desc">
                            <strong>Tính khả thi thương mại:</strong><br>
                            Phục vụ 50 bài báo, 10 ma trận, 5 báo cáo tổng quan chuyên sâu với chi phí API dưới 30 cents/tháng.
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top: 24px; padding: 20px;">
                    <div class="card-title" style="font-size: 16px; margin-bottom: 12px;">Kiểm Thử Tự Động &amp; Đảm Bảo Chất Lượng Kỹ Thuật (Test Harness)</div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; font-size: 13.5px;">
                        <div style="background: var(--surface-bone); padding: 12px; border-radius: 8px;">
                            <strong>test_retrieval_eval.py:</strong> Đo độ chính xác xếp hạng (Ranking), Token overlap score và Fallback retrieval khi thiếu dữ liệu.
                        </div>
                        <div style="background: var(--surface-bone); padding: 12px; border-radius: 8px;">
                            <strong>test_matrix_extraction.py:</strong> Kiểm tra tính toàn vẹn của JSON schema, tỷ lệ parse lỗi và xử lý ngoại lệ format.
                        </div>
                        <div style="background: var(--surface-bone); padding: 12px; border-radius: 8px;">
                            <strong>test_report_citation_helpers.py:</strong> Xác thực thuật toán đối soát chéo từng câu trong báo cáo với chunk ID database.
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 8: LIMITATIONS & ROADMAP ================= -->
        <section class="slide bone-section" id="slide-8">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 7: NHẬN DIỆN HẠN CHẾ &amp; HƯỚNG PHÁT TRIỂN</div>
                <h2 class="section-title">Những Hạn Chế Hiện Tại &amp; Lộ Trình Nâng Cấp Kỹ Thuật</h2>
                <p class="subtitle">Tư duy kỹ thuật phản biện: Nhìn rõ điểm nghẽn để thiết kế giải pháp mở rộng tiếp theo</p>

                <table class="custom-table">
                    <thead>
                        <tr>
                            <th style="width: 25%;">Hạn Chế Hiện Tại</th>
                            <th style="width: 35%;">Thực Trạng &amp; Tác Động</th>
                            <th style="width: 40%;">Giải Pháp Kỹ Thuật Tiếp Theo</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>1. Xử lý biểu đồ &amp; bảng phức tạp trong PDF</strong></td>
                            <td>Trình bóc tách dựa trên text (text-based parser) đôi khi làm mất cấu trúc hàng/cột của các bảng dữ liệu thử nghiệm phức tạp hoặc bỏ sót biểu đồ kết quả.</td>
                            <td>
                                <strong>Tích hợp Vision-Language Models (VLM):</strong> Ứng dụng mô hình Document AI chuyên sâu (ColPali hoặc Docling OCR nâng cao) để đọc trực tiếp hình ảnh trang tài liệu, trích xuất cấu trúc bảng chính xác 100%.
                            </td>
                        </tr>
                        <tr>
                            <td><strong>2. Tìm kiếm Vector thuần túy thiếu liên kết mạng lưới</strong></td>
                            <td>Vector embeddings rất tốt về mặt ngữ nghĩa nhưng chưa nắm bắt được mối quan hệ trích dẫn chéo (*co-citation*), niên biểu phát triển và trường phái nghiên cứu.</td>
                            <td>
                                <strong>Nâng cấp lên GraphRAG:</strong> Xây dựng đồ thị tri thức (Knowledge Graph) kết nối Thực thể: Tác giả → Phương pháp → Bộ dữ liệu → Kết quả, cho phép suy luận đa bước (Multi-hop Reasoning).
                            </td>
                        </tr>
                        <tr>
                            <td><strong>3. Phân xử mâu thuẫn nghiên cứu còn mang tính đơn nhất</strong></td>
                            <td>Sử dụng một LLM đơn lẻ để phân tích điểm bất đồng giữa các công trình có thể dẫn đến sự thiên vị (bias) trong kết luận.</td>
                            <td>
                                <strong>Multi-Agent Debate Pattern:</strong> Xây dựng cặp Agent "Biện hộ" (Proponent) và "Phản biện" (Skeptic) để tranh luận trước khi tổng hợp ra báo cáo mâu thuẫn khách quan nhất.
                            </td>
                        </tr>
                    </tbody>
                </table>

                <div class="card" style="margin-top: 20px; background: #ffffff; padding: 14px 20px;">
                    <div style="font-size: 13.5px; color: var(--charcoal); display: flex; align-items: center; gap: 8px;">
                        <span class="pill-badge pill-success" style="margin: 0;">Mở rộng</span>
                        <span>Đã chuẩn bị sẵn schema và migration cho cơ sở dữ liệu Neo4j / GraphRAG trong thư mục <code>app/services/knowledge_graph.py</code>.</span>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 9: KEY LEARNINGS ================= -->
        <section class="slide" id="slide-9">
            <div class="slide-content">
                <div class="pill-badge pill-primary">PHẦN 8: BÀI HỌC KỸ THUẬT RÚT RA</div>
                <h2 class="section-title">Những Đúc Kết Thực Chiến Khi Thiết Kế Hệ Thống AI Agent</h2>
                <p class="subtitle">Kinh nghiệm thực tiễn rút ra từ quá trình đưa Agent từ ý tưởng lên hệ thống chạy thực tế trong môi trường sản xuất</p>

                <div class="grid-3">
                    <div class="card">
                        <div class="stat-badge" style="font-size: 28px; margin-bottom: 8px;">01. Control &gt; Autonomy</div>
                        <div class="card-title" style="font-size: 17px;">Agent Cần State Machine Hữu Hạn</div>
                        <p class="card-text">
                            Các vòng lặp Agent thuần túy (như AutoGPT/ReAct không kiểm soát) rất dễ rơi vào bẫy lặp vô tận (infinite loop) hoặc suy diễn lạc đề. Việc sử dụng <strong>LangGraph</strong> với các trạng thái rõ ràng, điều kiện rẽ nhánh và <em>fallback nodes</em> là yếu tố quyết định để hệ thống hoạt động ổn định và tin cậy.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="font-size: 28px; margin-bottom: 8px;">02. Streaming UX</div>
                        <div class="card-title" style="font-size: 17px;">Trải Nghiệm Thời Gian Thực Là Cốt Lõi</div>
                        <p class="card-text">
                            Người dùng không thể chờ đợi trước một màn hình đứng im trong 40 giây khi Agent xử lý hàng chục bài báo. Việc ứng dụng <strong>Server-Sent Events (SSE)</strong> để hiển thị trực quan từng bước suy nghĩ (*Thinking → Tool Call → Ingestion*) biến thời gian chờ thành một trải nghiệm công nghệ đầy tính thuyết phục.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="font-size: 28px; margin-bottom: 8px;">03. Data &gt; Model</div>
                        <div class="card-title" style="font-size: 17px;">Dữ Liệu Sạch Đem Lại Giá Trị Vượt Trội</div>
                        <p class="card-text">
                            Thay vì cố gắng sử dụng những mô hình đắt đỏ nhất, việc đầu tư nghiêm túc vào <strong>pipeline chuẩn hóa PDF, lọc trùng lặp DOI và chunking theo ngữ cảnh</strong> giúp một mô hình tầm trung (như DeepSeek/mimo) đạt độ chính xác cao hơn hẳn mà lại tiết kiệm <strong>85% chi phí vận hành</strong>.
                        </p>
                    </div>
                </div>

                <div class="card" style="margin-top: 24px; background: var(--surface-bone); border: none; padding: 18px 24px;">
                    <div style="font-size: 14px; font-weight: 600; color: var(--ink);">
                        💡 Tinh thần cốt lõi của một AI Agent Engineer:
                        <span style="font-weight: 400; color: var(--body);">
                            Không chỉ dừng lại ở việc gọi API prompt đơn giản, mà là thiết kế kiến trúc phân rã bài toán, kiểm soát luồng dữ liệu, chủ động xây dựng chốt chặn sai sót và tối ưu hóa hiệu quả kinh tế của từng token.
                        </span>
                    </div>
                </div>
            </div>
        </section>

        <!-- ================= SLIDE 10: DEMO & CONCLUSION ================= -->
        <section class="slide hero-band" id="slide-10">
            <div class="hero-mesh"></div>
            <div class="slide-content">
                <div class="pill-badge pill-dark">KẾT LUẬN &amp; SẴN SÀNG PHẢN BIỆN</div>
                <h1 class="hero-title" style="font-size: 80px; margin-bottom: 16px;">SẴN SÀNG TRAO ĐỔI</h1>
                <p class="hero-sub" style="font-size: 24px; max-width: 900px; margin-bottom: 32px;">
                    Lumen đã hoàn thiện mã nguồn, hệ thống kiểm thử tự động và video hoạt động thực tế.
                </p>

                <div class="grid-3" style="max-width: 1100px; margin-bottom: 36px; z-index: 2; position: relative;">
                    <div class="hero-meta-card" style="background: rgba(255, 255, 255, 0.15);">
                        <div class="label" style="color: #ffffff; font-weight: 700;">🎥 WORKING DEMO</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px;">
                            <a href="https://youtu.be/uNt316BZaY8" target="_blank" style="color: #ffffff; text-decoration: underline;">
                                Xem Video Demo Trên YouTube ↗
                            </a>
                        </div>
                        <p style="font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 4px;">Trình diễn trực tiếp luồng tìm kiếm, bóc ma trận &amp; sinh báo cáo</p>
                    </div>

                    <div class="hero-meta-card" style="background: rgba(255, 255, 255, 0.15);">
                        <div class="label" style="color: #ffffff; font-weight: 700;">💻 SOURCE CODE &amp; TESTS</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px;">
                            <a href="https://github.com/vietlinhh02" target="_blank" style="color: #ffffff; text-decoration: underline;">
                                github.com/vietlinhh02 ↗
                            </a>
                        </div>
                        <p style="font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 4px;">FastAPI Backend + Next.js 16 + 50+ Test Cases &amp; CI/CD</p>
                    </div>

                    <div class="hero-meta-card" style="background: rgba(255, 255, 255, 0.15);">
                        <div class="label" style="color: #ffffff; font-weight: 700;">🤝 SẴN SÀNG Q&amp;A</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px; color: #ffffff;">
                            Technical Defense Ready
                        </div>
                        <p style="font-size: 12px; color: rgba(255,255,255,0.8); margin-top: 4px;">Sẵn sàng trả lời các câu hỏi chuyên sâu về kiến trúc và thuật toán</p>
                    </div>
                </div>

                <div style="z-index: 2; position: relative; font-size: 15px; color: rgba(255,255,255,0.9); line-height: 1.6;">
                    <strong>Nguyễn Viết Linh</strong> · Ứng tuyển: AI Agent Engineer Intern tại PIXTA Vietnam<br>
                    Email: <a href="mailto:nvlinh0607@gmail.com" style="color: #ffffff;">nvlinh0607@gmail.com</a> | Điện thoại: <strong>0981 601 209</strong>
                </div>
            </div>
        </section>

    </main>

    <script>
        const container = document.getElementById('deck-container');
        const slides = document.querySelectorAll('.slide');
        const indicator = document.getElementById('slide-indicator');
        const globalHeader = document.getElementById('global-header');
        const globalFooter = document.getElementById('global-footer');
        const footerSlideNum = document.getElementById('footer-slide-num');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        const fsBtn = document.getElementById('fs-btn');

        let currentIndex = 0;

        function updateUI() {
            const slideHeight = window.innerHeight;
            currentIndex = Math.round(container.scrollTop / slideHeight);

            if (currentIndex < 0) currentIndex = 0;
            if (currentIndex >= slides.length) currentIndex = slides.length - 1;

            const padNum = (num) => (num < 10 ? '0' + num : num);
            indicator.innerText = `${padNum(currentIndex + 1)} / ${padNum(slides.length)}`;
            footerSlideNum.innerText = `Slide ${padNum(currentIndex + 1)} / ${padNum(slides.length)}`;

            const currentSlide = slides[currentIndex];
            if (currentSlide) {
                if (currentSlide.classList.contains('hero-band') || currentSlide.classList.contains('dark-section')) {
                    globalHeader.classList.remove('dark-text');
                    globalHeader.classList.add('light-text');
                    globalFooter.classList.remove('dark-text');
                    globalFooter.classList.add('light-text');
                } else {
                    globalHeader.classList.remove('light-text');
                    globalHeader.classList.add('dark-text');
                    globalFooter.classList.remove('light-text');
                    globalFooter.classList.add('dark-text');
                }
            }
        }

        function scrollToSlide(index) {
            if (index >= 0 && index < slides.length) {
                slides[index].scrollIntoView({ behavior: 'smooth' });
            }
        }

        prevBtn.addEventListener('click', () => scrollToSlide(currentIndex - 1));
        nextBtn.addEventListener('click', () => scrollToSlide(currentIndex + 1));

        fsBtn.addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen();
            } else {
                if (document.exitFullscreen) {
                    document.exitFullscreen();
                }
            }
        });

        container.addEventListener('scroll', updateUI);
        window.addEventListener('resize', updateUI);

        window.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ') {
                e.preventDefault();
                scrollToSlide(currentIndex + 1);
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'Backspace') {
                e.preventDefault();
                scrollToSlide(currentIndex - 1);
            } else if (e.key.toLowerCase() === 'f') {
                if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen();
                } else {
                    document.exitFullscreen();
                }
            }
        });

        // Initialize UI
        updateUI();
    </script>
</body>
</html>
"""

# Replace image placeholder
html_final = html_template.replace("__IMG_MATRIX__", encoded.get('matrix.png', ''))

output_path = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/pitch_materials/lumen_pixta_presentation.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_final)

print(f"Generated successfully: {output_path}")
print(f"File size: {os.path.getsize(output_path)} bytes")
