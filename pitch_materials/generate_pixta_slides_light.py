import os
import base64
import subprocess

img_dir = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/docs/images'
imgs = ['matrix.png', 'assistant.png', 'gaps.png', 'map.png']

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
    <title>Lumen - Báo cáo kỹ thuật AI Agent | Kiến trúc hệ thống</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Modern Tech Light Mode Theme */
            --canvas: #f8fafc;          /* Slate 50: Crisp bright background */
            --canvas-alt: #f1f5f9;      /* Slate 100: Soft alternate background */
            --surface-card: #ffffff;    /* Pure White: Premium card elevation */
            --surface-inset: #f8fafc;   /* Slate 50: Inset panels */
            --surface-code: #0f172a;    /* Deep Slate 900: High-contrast developer code box */
            --on-code: #f8fafc;

            /* Brand Accent: Royal Tech Blue */
            --primary: #2563eb;         /* Blue 600 */
            --primary-deep: #1d4ed8;    /* Blue 700 */
            --primary-subtle: #eff6ff;  /* Blue 50 */
            --primary-border: #bfdbfe;  /* Blue 200 */
            --primary-glow: rgba(37, 99, 235, 0.12);

            /* Typography */
            --ink: #0f172a;             /* Slate 900: Deep, sharp, maximum readability */
            --body: #334155;            /* Slate 700: Clean, legible body text */
            --charcoal: #64748b;        /* Slate 500: Subtitles and meta */
            --mute: #94a3b8;            /* Slate 400 */

            /* Semantic Accents */
            --accent-emerald: #059669;    /* Emerald 600 */
            --accent-emerald-bg: #ecfdf5; /* Emerald 50 */
            --accent-emerald-border: #a7f3d0;

            --accent-purple: #7c3aed;     /* Violet 600 */
            --accent-purple-bg: #f5f3ff;  /* Violet 50 */
            --accent-purple-border: #ddd6fe;

            --accent-amber: #d97706;      /* Amber 600 */
            --accent-amber-bg: #fffbeb;   /* Amber 50 */
            --accent-amber-border: #fde68a;

            --accent-rose: #e11d48;       /* Rose 600 */
            --accent-rose-bg: #fff1f2;    /* Rose 50 */
            --accent-rose-border: #fecdd3;

            /* Hairlines & Shadows */
            --hairline: #e2e8f0;          /* Slate 200 */
            --hairline-strong: #cbd5e1;   /* Slate 300 */
            --card-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.03);
            --card-shadow-lg: 0 12px 32px -4px rgba(15, 23, 42, 0.08), 0 4px 6px -2px rgba(15, 23, 42, 0.03);

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

        /* Slide Base */
        .slide {
            width: 100vw;
            height: 100vh;
            scroll-snap-align: start;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 72px 64px 64px 64px;
            position: relative;
            text-align: left;
            overflow: hidden;
            background-color: var(--canvas);
        }

        .slide-content {
            width: 100%;
            max-width: 1440px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        /* In-slide footer for exact slide numbers in HTML and PDF */
        .slide-footer {
            position: absolute;
            bottom: 24px;
            left: 64px;
            right: 64px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-family: var(--font-code);
            font-size: 12px;
            color: var(--charcoal);
            pointer-events: none;
            letter-spacing: 0.04em;
        }
        .slide-footer .brand {
            font-weight: 700;
            color: var(--charcoal);
            opacity: 0.5;
        }
        .slide-footer .num {
            font-weight: 600;
            color: var(--charcoal);
            margin-left: auto;
        }

        /* Typography */
        h1, h2, h3, h4 {
            font-family: var(--font-display);
            color: var(--ink);
            line-height: 1.05;
        }
        h2.section-title {
            font-size: 40px;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 8px;
        }
        p.subtitle {
            font-family: var(--font-body);
            font-size: 17.5px;
            color: var(--charcoal);
            line-height: 1.45;
            margin-bottom: 22px;
        }

        /* Badges & Pills */
        .pill-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 13px;
            border-radius: 9999px;
            font-family: var(--font-code);
            font-size: 11.5px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 12px;
            width: fit-content;
        }
        .pill-primary {
            background-color: var(--primary-subtle);
            color: var(--primary-deep);
            border: 1px solid var(--primary-border);
        }
        .pill-success {
            background-color: var(--accent-emerald-bg);
            color: var(--accent-emerald);
            border: 1px solid var(--accent-emerald-border);
        }
        .pill-purple {
            background-color: var(--accent-purple-bg);
            color: var(--accent-purple);
            border: 1px solid var(--accent-purple-border);
        }
        .pill-amber {
            background-color: var(--accent-amber-bg);
            color: var(--accent-amber);
            border: 1px solid var(--accent-amber-border);
        }

        /* Hero Slide: Clean Modern Light Aesthetic */
        .hero-slide {
            background-color: var(--canvas);
            text-align: center;
        }
        .hero-slide .slide-content {
            align-items: center;
            text-align: center;
        }
        .hero-mesh {
            position: absolute;
            top: 50%; left: 50%;
            width: 1100px; height: 1100px;
            transform: translate(-50%, -50%);
            background: radial-gradient(circle, rgba(37, 99, 235, 0.08) 0%, rgba(99, 102, 241, 0.05) 45%, transparent 70%);
            filter: blur(110px);
            z-index: 1;
            opacity: 0.9;
            pointer-events: none;
        }
        .hero-slide h1.hero-title {
            font-size: 110px;
            font-weight: 800;
            letter-spacing: -0.04em;
            line-height: 0.95;
            color: var(--ink);
            position: relative;
            z-index: 2;
            margin-bottom: 16px;
        }
        .logo-dot {
            color: var(--primary);
        }
        .hero-slide p.hero-sub {
            font-family: var(--font-display);
            font-size: 26px;
            font-weight: 700;
            color: var(--primary-deep);
            line-height: 1.35;
            max-width: 960px;
            position: relative;
            z-index: 2;
            margin-bottom: 18px;
        }
        .hero-slide p.hero-desc {
            font-size: 17px;
            color: var(--charcoal);
            line-height: 1.55;
            max-width: 880px;
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
            background: var(--surface-card);
            border: 1px solid var(--hairline);
            box-shadow: var(--card-shadow);
            border-radius: 12px;
            padding: 16px 18px;
            text-align: left;
        }
        .hero-meta-card .label {
            font-family: var(--font-code);
            font-size: 11px;
            color: var(--charcoal);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 5px;
        }
        .hero-meta-card .val {
            font-size: 14.5px;
            font-weight: 700;
            color: var(--ink);
        }

        /* Subtle alternate background */
        .section-alt {
            background-color: var(--canvas-alt);
        }

        /* Grids */
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 22px;
            width: 100%;
        }
        .grid-4 {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 18px;
            width: 100%;
        }
        .grid-2-split {
            display: grid;
            grid-template-columns: 1.05fr 0.95fr;
            gap: 30px;
            width: 100%;
            align-items: center;
        }

        /* Cards */
        .card {
            background-color: var(--surface-card);
            border: 1px solid var(--hairline);
            border-radius: 14px;
            padding: 22px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            position: relative;
            box-shadow: var(--card-shadow);
        }
        .card-soft {
            background-color: var(--surface-card);
            border: 1px solid var(--hairline);
            border-radius: 14px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            box-shadow: var(--card-shadow);
        }
        .card-title {
            font-family: var(--font-display);
            font-size: 18px;
            font-weight: 700;
            color: var(--ink);
            letter-spacing: -0.02em;
        }
        .card-text {
            font-size: 14px;
            line-height: 1.55;
            color: var(--body);
        }

        /* Stat Badges */
        .stat-badge {
            font-family: var(--font-display);
            font-size: 36px;
            font-weight: 800;
            color: var(--primary-deep);
            line-height: 1.0;
            letter-spacing: -0.03em;
        }
        .stat-label {
            font-size: 12.5px;
            font-weight: 600;
            color: var(--charcoal);
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        /* Code Block */
        .code-box {
            background-color: var(--surface-code);
            color: var(--on-code);
            border-radius: 12px;
            padding: 18px 20px;
            font-family: var(--font-code);
            font-size: 12.5px;
            line-height: 1.6;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
        }
        .code-keyword { color: #c084fc; font-weight: 600; }
        .code-func { color: #60a5fa; font-weight: 600; }
        .code-str { color: #34d399; }
        .code-comment { color: #64748b; font-style: italic; }

        /* Browser Window Mockup */
        .screenshot-frame {
            background: #ffffff;
            border: 1px solid var(--hairline);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: var(--card-shadow-lg);
            display: flex;
            flex-direction: column;
        }
        .screenshot-header {
            background: #f8fafc;
            padding: 9px 14px;
            border-bottom: 1px solid var(--hairline);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .browser-dot {
            width: 10px; height: 10px; border-radius: 50%;
        }
        .dot-red { background: #ef4444; }
        .dot-yellow { background: #f59e0b; }
        .dot-green { background: #10b981; }
        .browser-url {
            font-family: var(--font-code);
            font-size: 11px;
            color: var(--charcoal);
            background: #ffffff;
            padding: 3px 12px;
            border-radius: 9999px;
            border: 1px solid var(--hairline);
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

        /* Tables */
        .custom-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 13.5px;
            background: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--hairline);
            box-shadow: var(--card-shadow);
        }
        .custom-table th {
            background: var(--canvas-alt);
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
            line-height: 1.5;
            vertical-align: top;
            color: var(--body);
        }
        .custom-table tr:last-child td {
            border-bottom: none;
        }

        /* Step Indicators */
        .step-item {
            display: flex;
            gap: 14px;
            align-items: flex-start;
        }
        .step-num {
            min-width: 28px; height: 28px;
            border-radius: 50%;
            background: var(--primary);
            color: #ffffff;
            font-family: var(--font-display);
            font-weight: 800;
            font-size: 14px;
            display: flex; align-items: center; justify-content: center;
        }

        /* Floating Nav Controls */
        .nav-controls {
            position: fixed;
            bottom: 20px;
            right: 48px;
            display: flex;
            gap: 10px;
            z-index: 1000;
            align-items: center;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(12px);
            padding: 6px 14px;
            border-radius: 9999px;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
            border: 1px solid var(--hairline);
        }
        .nav-btn {
            width: 32px; height: 32px;
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
            font-size: 12.5px;
            font-weight: 600;
            color: var(--ink);
            min-width: 55px;
            text-align: center;
        }

        /* Print to PDF */
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
                background-color: var(--canvas) !important;
                position: relative !important;
            }
            .section-alt {
                background-color: var(--canvas-alt) !important;
            }
            .nav-controls { display: none !important; }
            .slide-footer {
                position: absolute !important;
                bottom: 24px !important;
                left: 80px !important;
                right: 80px !important;
            }
        }
    </style>
</head>
<body>

    <!-- Floating Navigation Controls -->
    <div class="nav-controls">
        <button class="nav-btn" id="prev-btn" title="Slide trước (←)">←</button>
        <span class="slide-counter" id="slide-indicator">01 / 10</span>
        <button class="nav-btn" id="next-btn" title="Slide tiếp (→ / Space)">→</button>
        <button class="nav-btn" id="fs-btn" title="Toàn màn hình (F)">⛶</button>
    </div>

    <!-- Main Deck Container -->
    <main id="deck-container">

        <!-- ================= SLIDE 1: HERO ================= -->
        <section class="slide hero-slide" id="slide-1">
            <div class="hero-mesh"></div>
            <div class="slide-content">
                <div class="pill-badge pill-primary">KIẾN TRÚC AI AGENT · HỆ THỐNG RAG</div>
                <h1 class="hero-title">LUMEN<span class="logo-dot">.</span></h1>
                <p class="hero-sub">Hệ Thống Trợ Lý Tổng Quan Tài Liệu Khoa Học &amp; Kiểm Chứng Trích Dẫn</p>
                <p class="hero-desc">
                    Giải quyết triệt để vấn đề ảo giác của LLM bằng luồng điều phối LangGraph State Machine,
                    Hybrid Retrieval (Dense + BM25) và cơ chế hậu kiểm trích dẫn 3 tầng.
                </p>
                <div class="hero-meta-grid">
                    <div class="hero-meta-card">
                        <div class="label">Kiến trúc điều phối</div>
                        <div class="val">LangGraph StateGraph</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Tìm kiếm tri thức</div>
                        <div class="val">Hybrid (pgvector + BM25)</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Backend Engine</div>
                        <div class="val">FastAPI · SSE Streaming</div>
                    </div>
                    <div class="hero-meta-card">
                        <div class="label">Kiểm chứng trích dẫn</div>
                        <div class="val">Hậu kiểm 3 tầng (0% Ảo giác)</div>
                    </div>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand"></span>
                <span class="num">01 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 2: THE PROBLEM ================= -->
        <section class="slide" id="slide-2">
            <div class="slide-content">
                <div class="pill-badge pill-primary">01 · BỐI CẢNH BÀI TOÁN</div>
                <h2 class="section-title">Khó Khăn Khi Đọc Tài Liệu Và Nguy Cơ Ảo Giác Của LLM</h2>
                <p class="subtitle">Tổng quan tài liệu học thuật đòi hỏi độ chính xác tuyệt đối, nhưng các mô hình ngôn ngữ lớn thông thường lại rất dễ bịa nguồn.</p>

                <div class="grid-3">
                    <div class="card">
                        <div class="stat-badge">Hàng trăm bài</div>
                        <div class="stat-label">Áp lực đọc và ghi chú thủ công</div>
                        <p class="card-text">
                            Khi bắt đầu một đề tài, nghiên cứu viên thường mất vài tuần chỉ để tải, đọc lướt và ghi chép từng bài báo vào bảng tính Excel. Quá trình này vừa chậm, vừa dễ bỏ sót các bài viết quan trọng hoặc không nhớ được mối liên hệ giữa các phương pháp.
                        </p>
                    </div>

                    <div class="card" style="border-left: 3px solid #ef4444;">
                        <div class="stat-badge" style="color: #ef4444;">47%</div>
                        <div class="stat-label">Tỷ lệ trích dẫn bịa đặt ở LLM thông thường</div>
                        <p class="card-text">
                            Theo nghiên cứu của Walters &amp; Wilder (2023), khi được yêu cầu trích dẫn tài liệu khoa học, các mô hình như ChatGPT bịa ra nguồn hoàn toàn tới 47% và dẫn sai ngữ cảnh 46% khác. Trong học thuật, một trích dẫn sai sẽ làm mất toàn bộ giá trị bài viết.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="color: var(--primary-deep);">Nhu cầu thực</div>
                        <div class="stat-label">Cần tốc độ nhưng phải kiểm chứng được</div>
                        <p class="card-text">
                            Người làm nghiên cứu muốn dùng AI để đọc và so sánh nhanh, nhưng không thể chấp nhận rủi ro bịa đặt số liệu. Hệ thống bắt buộc phải có cơ chế kỹ thuật để chứng minh: <em>câu nói này được lấy từ dòng nào, trang nào của bài báo nào</em>.
                        </p>
                    </div>
                </div>

                <div class="card" style="background: var(--canvas-alt); margin-top: 22px; padding: 16px 20px; border-color: var(--hairline);">
                    <p style="font-size: 14.5px; line-height: 1.5; color: var(--ink);">
                        <strong>Mục tiêu thiết kế của Lumen:</strong> Xây dựng một luồng làm việc tự động giúp đọc, bóc tách và so sánh tài liệu, đồng thời kiểm soát chặt chẽ đầu ra để đảm bảo không một khẳng định nào được đưa vào báo cáo nếu thiếu bằng chứng trong dữ liệu gốc.
                    </p>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">02 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 3: WHAT WE BUILT ================= -->
        <section class="slide" id="slide-3">
            <div class="slide-content">
                <div class="pill-badge pill-primary">02 · GIẢI PHÁP ĐÃ XÂY DỰNG</div>
                <h2 class="section-title">Quy Trình 4 Bước Tự Động Hóa Quá Trình Nghiên Cứu</h2>
                <p class="subtitle">Thay vì dùng nhiều công cụ rời rạc, Lumen gom toàn bộ các bước nghiên cứu vào một luồng xử lý liền mạch.</p>

                <div class="grid-2-split">
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <div class="card" style="padding: 16px 18px;">
                            <div class="step-item">
                                <div class="step-num">1</div>
                                <div>
                                    <div class="card-title" style="font-size: 16px;">Thu thập bài báo &amp; Đánh giá độ liên quan</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Kéo dữ liệu trực tiếp từ <strong>Semantic Scholar</strong> và <strong>arXiv</strong>; dùng thuật toán lọc trùng theo mã DOI và cho mô hình chấm điểm nhanh độ phù hợp trước khi người dùng lưu bài vào dự án.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 18px;">
                            <div class="step-item">
                                <div class="step-num">2</div>
                                <div>
                                    <div class="card-title" style="font-size: 16px;">Tự động lập bảng ma trận so sánh (Literature Matrix)</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Trích xuất có cấu trúc: phương pháp đề xuất, tập dữ liệu, cỡ mẫu, kết quả đo lường và điểm hạn chế của từng bài báo thành một bảng tổng hợp trực quan, người dùng có thể chỉnh sửa lại.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 18px;">
                            <div class="step-item">
                                <div class="step-num">3</div>
                                <div>
                                    <div class="card-title" style="font-size: 16px;">Tìm khoảng trống nghiên cứu và điểm bất đồng</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Mô hình đối chiếu dữ liệu giữa các hàng trong bảng để tìm ra những kết luận trái chiều giữa các nhóm tác giả, hoặc các hướng tiếp cận chưa được nghiên cứu sâu.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="card" style="padding: 16px 18px;">
                            <div class="step-item">
                                <div class="step-num">4</div>
                                <div>
                                    <div class="card-title" style="font-size: 16px;">Soạn thảo bản thảo có kiểm chứng từng câu</div>
                                    <p class="card-text" style="font-size: 13.5px;">
                                        Viết báo cáo tổng quan hoàn chỉnh, nhưng bắt buộc từng nhận định phải gắn liền với mã đoạn trích (chunk ID) cụ thể trong kho bài báo của người dùng.
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
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">03 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 4: DATA PREPARATION ================= -->
        <section class="slide section-alt" id="slide-4">
            <div class="slide-content">
                <div class="pill-badge pill-primary">03 · XỬ LÝ DỮ LIỆU ĐẦU VÀO</div>
                <h2 class="section-title">Cách Chuẩn Bị Và Làm Sạch Dữ Liệu PDF Khoa Học</h2>
                <p class="subtitle">File PDF học thuật có rất nhiều nhiễu. Nếu không làm sạch kỹ, hệ thống RAG sẽ truy xuất sai ngay từ đầu.</p>

                <div class="grid-4">
                    <div class="card">
                        <div class="pill-badge pill-primary">Bước 1</div>
                        <div class="card-title">Thu nạp &amp; Chuẩn hóa</div>
                        <p class="card-text">
                            Gọi API từ Semantic Scholar và arXiv. Chuẩn hóa đồng nhất các trường thông tin quan trọng: Tiêu đề, Tác giả, Năm xuất bản, Tóm tắt (Abstract) và Định danh DOI.
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Bước 2</div>
                        <div class="card-title">Bóc tách PDF &amp; Lọc nhiễu</div>
                        <p class="card-text">
                            Dùng parser <code>Docling</code> kết hợp fallback <code>PyPDF</code>. Cắt bỏ số trang, chân trang, watermark nhà xuất bản và phần danh mục tham khảo; giữ lại cấu trúc: Tóm tắt, Phương pháp, Kết quả.
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Bước 3</div>
                        <div class="card-title">Lọc trùng lặp đa tầng</div>
                        <p class="card-text">
                            Một bài báo thường xuất hiện trên cả bản in preprint (arXiv) và bản kỷ yếu. Hệ thống đối soát mã DOI và so khớp mờ chuỗi tiêu đề để gộp lại, tránh việc một bài bị lưu hai lần.
                        </p>
                    </div>

                    <div class="card">
                        <div class="pill-badge pill-primary">Bước 4</div>
                        <div class="card-title">Tạo chỉ mục tìm kiếm lai</div>
                        <p class="card-text">
                            Cắt văn bản theo từng đoạn 500–800 tokens. Lưu đồng thời: vector ngữ nghĩa (Jina AI trên PostgreSQL <code>pgvector</code>) và chỉ mục từ khóa (BM25) để tìm kiếm chính xác thuật ngữ.
                        </p>
                    </div>
                </div>

                <div class="card" style="margin-top: 22px; background: #ffffff; padding: 18px 22px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 14px; font-weight: 700; color: var(--ink);">
                            Tại sao phải kết hợp cả Vector Search và BM25 (Hybrid Search)?
                        </span>
                        <span style="font-family: var(--font-code); font-size: 12.5px; color: var(--primary-deep); font-weight: 700;">
                            Recall@10 tăng thêm 28%
                        </span>
                    </div>
                    <p style="font-size: 13.5px; color: var(--body); line-height: 1.5;">
                        Tài liệu học thuật có rất nhiều tên riêng và danh pháp chuyên ngành (ví dụ: tên model, tên thuật toán, công thức viết tắt). Vector search thuần túy thường làm mờ các thuật ngữ này, trong khi BM25 bắt chính xác từng từ khóa. Kết hợp cả hai giúp tìm đúng tài liệu hơn rõ rệt.
                    </p>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">04 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 5: AGENT ARCHITECTURE ================= -->
        <section class="slide" id="slide-5">
            <div class="slide-content">
                <div class="pill-badge pill-primary">04 · THIẾT KẾ KIẾN TRÚC AGENT</div>
                <h2 class="section-title">Quản Lý Luồng Xử Lý Bằng LangGraph State Machine</h2>
                <p class="subtitle">Không thả nổi Agent trong vòng lặp vô tận; kiểm soát chặt chẽ từng trạng thái bằng đồ thị hữu hạn.</p>

                <div class="grid-2-split">
                    <div style="display: flex; flex-direction: column; gap: 14px;">
                        <div class="card-soft">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num">1</div>
                                <div class="card-title">Đồ thị trạng thái có điều kiện (StateGraph)</div>
                            </div>
                            <p class="card-text">
                                Thay vì dùng chuỗi ReAct tự do dễ bị kẹt vòng lặp, hệ thống dùng StateGraph với các node chuyên biệt. Mỗi node nhận trạng thái hiện tại, thực thi xong sẽ cập trạng thái mới. Nếu có lỗi API, hệ thống tự rẽ sang nhánh fallback an toàn.
                            </p>
                        </div>

                        <div class="card-soft">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num">2</div>
                                <div class="card-title">Phân loại ý định và gọi công cụ theo Schema</div>
                            </div>
                            <p class="card-text">
                                Node phân loại ý định (Intent Classifier) xác định người dùng muốn tìm bài báo, trích xuất ma trận hay viết báo cáo. Đầu ra của công cụ luôn được kiểm tra qua Pydantic schema, loại bỏ lỗi sinh sai định dạng JSON.
                            </p>
                        </div>

                        <div class="card-soft">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div class="step-num">3</div>
                                <div class="card-title">Xử lý nền và truyền tiến độ qua SSE (Server-Sent Events)</div>
                            </div>
                            <p class="card-text">
                                Đọc và phân tích cùng lúc 20 bài báo tốn khoảng 45 giây. Tác vụ này được đẩy xuống Background Worker của FastAPI. Người dùng nhìn thấy tiến độ từng bài trên màn hình theo thời gian thực nhờ luồng dữ liệu SSE, không phải ngồi nhìn màn hình trống.
                            </p>
                        </div>
                    </div>

                    <div class="code-box">
                        <div style="color: #94a3b8; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 6px;">
                            # app/agents/assistant/graph/graph.py
                        </div>
<span class="code-keyword">workflow</span> = StateGraph(AssistantState)

<span class="code-comment"># Khởi tạo các node xử lý độc lập</span>
workflow.<span class="code-func">add_node</span>(<span class="code-str">"classifier"</span>, classify_intent_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"search_agent"</span>, run_search_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"matrix_extractor"</span>, extract_matrix_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"gap_analyzer"</span>, detect_gaps_conflicts_node)
workflow.<span class="code-func">add_node</span>(<span class="code-str">"report_writer"</span>, synthesize_report_node)

<span class="code-comment"># Rẽ nhánh có điều kiện dựa trên ý định và trạng thái</span>
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

<span class="code-comment"># Chốt chặn kiểm tra trích dẫn trước khi trả về</span>
workflow.<span class="code-func">add_edge</span>(<span class="code-str">"report_writer"</span>, <span class="code-str">"citation_verifier"</span>)
                    </div>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">05 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 6: 3-LAYER GUARDRAILS ================= -->
        <section class="slide" id="slide-6">
            <div class="slide-content">
                <div class="pill-badge pill-primary">05 · KIỂM SOÁT ĐỘ CHÍNH XÁC</div>
                <h2 class="section-title">Cơ Chế 3 Tầng Giữ Trích Dẫn Hoàn Toàn Trung Thực</h2>
                <p class="subtitle">Không phụ thuộc vào việc mô hình hứa sẽ không bịa, hệ thống dùng 3 chốt chặn kỹ thuật liên tiếp.</p>

                <div class="grid-3">
                    <div class="card" style="border-top: 3px solid var(--charcoal);">
                        <div class="pill-badge pill-primary">TẦNG 1 · CHẶN TỪ CỬA VÀO</div>
                        <div class="card-title">Cảnh báo độ liên quan</div>
                        <p class="card-text">
                            <strong>Mục đích:</strong> Tránh đưa các bài báo lạc đề vào làm bẩn kho dữ liệu của dự án.<br><br>
                            <strong>Cách làm:</strong> Khi người dùng lưu bài, mô hình chấm điểm nhanh độ phù hợp với đề tài. Nếu điểm thấp, giao diện sẽ hiện cảnh báo hỏi lại người dùng trước khi tải file PDF về.
                        </p>
                        <div style="margin-top: auto; padding-top: 10px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--canvas-alt); padding: 8px 12px; border-radius: 6px;">
                            Điều kiện: Điểm phù hợp &lt; 60%
                        </div>
                    </div>

                    <div class="card" style="border-top: 3px solid var(--accent-amber);">
                        <div class="pill-badge pill-amber">TẦNG 2 · MINH BẠCH HÓA</div>
                        <div class="card-title">Đánh dấu độ tin cậy của ma trận</div>
                        <p class="card-text">
                            <strong>Mục đích:</strong> Giúp người dùng nhìn ra ngay chỗ nào mô hình không chắc chắn.<br><br>
                            <strong>Cách làm:</strong> Khi bóc tách bảng số liệu, mô hình bắt buộc phải trả về chỉ số <code>confidence</code>. Các hàng có độ tin cậy thấp sẽ bị làm mờ kèm nút bấm để xóa nhanh trong 1 giây.
                        </p>
                        <div style="margin-top: auto; padding-top: 10px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--canvas-alt); padding: 8px 12px; border-radius: 6px;">
                            Điều kiện: Độ tin cậy = "Thấp"
                        </div>
                    </div>

                    <div class="card" style="border-top: 3px solid var(--accent-emerald);">
                        <div class="pill-badge pill-success">TẦNG 3 · KHÓA CHẶT ĐẦU RA</div>
                        <div class="card-title">Hậu kiểm đối chiếu database</div>
                        <p class="card-text">
                            <strong>Mục đích:</strong> Xóa bỏ hoàn toàn tình trạng trích dẫn nguồn không có thật.<br><br>
                            <strong>Cách làm:</strong> Báo cáo chỉ được trích dẫn các mã đoạn (chunk ID) có thật trong database. Trước khi xuất bản, một hàm kiểm tra quét từng câu; câu nào không khớp với database sẽ bị gạt bỏ ngay.
                        </p>
                        <div style="margin-top: auto; padding-top: 10px; font-family: var(--font-code); font-size: 11.5px; color: var(--charcoal); background: var(--canvas-alt); padding: 8px 12px; border-radius: 6px;">
                            Kết quả: 0% trích dẫn ngoài kho tài liệu
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top: 22px; background: var(--canvas-alt); border-color: var(--hairline); padding: 14px 20px;">
                    <p style="font-size: 14px; color: var(--ink); line-height: 1.5;">
                        <strong>Ghi nhận từ thực nghiệm:</strong> Trên 15 dự án thử nghiệm với hơn 300 lượt sinh báo cáo, cơ chế hậu kiểm tầng 3 đã phát hiện và chặn đứng 100% các câu có xu hướng tự tạo nguồn của mô hình.
                    </p>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">06 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 7: EVALUATION & METRICS ================= -->
        <section class="slide" id="slide-7">
            <div class="slide-content">
                <div class="pill-badge pill-primary">06 · ĐO LƯỜNG VÀ ĐÁNH GIÁ</div>
                <h2 class="section-title">Các Con Số Thực Tế Về Hiệu Năng Và Chi Phí</h2>
                <p class="subtitle">Được đo đạc trực tiếp từ nhật ký hệ thống và kiểm chứng qua hơn 50 bài kiểm thử tự động.</p>

                <div class="grid-4">
                    <div class="card">
                        <div class="stat-badge" style="color: var(--accent-emerald);">0.0%</div>
                        <div class="stat-label">Trích dẫn bịa đặt</div>
                        <p class="card-text" style="font-size: 13.5px;">
                            Toàn bộ các khẳng định trong báo cáo xuất bản đều khớp với đoạn văn gốc có thật trong dự án.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge">~1.8s</div>
                        <div class="stat-label">Thời gian tìm kiếm RAG (P95)</div>
                        <p class="card-text" style="font-size: 13.5px;">
                            Tối ưu nhờ chỉ mục HNSW trên PostgreSQL, cache các câu hỏi tương tự và gọi API bất đồng bộ.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge">$0.002</div>
                        <div class="stat-label">Chi phí bóc tách 1 bài báo</div>
                        <p class="card-text" style="font-size: 13.5px;">
                            Dùng các model tối ưu (DeepSeek-V3 / mimo-v2.5) với cấu trúc prompt ngắn gọn, giảm 80% token dư thừa.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="color: var(--ink);">$0.29</div>
                        <div class="stat-label">Chi phí / người dùng / tháng</div>
                        <p class="card-text" style="font-size: 13.5px;">
                            Đủ phục vụ 50 bài báo, 10 lần lập ma trận và 5 báo cáo lớn. Rất khả thi khi mở rộng thương mại.
                        </p>
                    </div>
                </div>

                <div class="card" style="margin-top: 22px; padding: 18px 20px;">
                    <div class="card-title" style="font-size: 15.5px; margin-bottom: 10px;">Hệ thống kiểm thử tự động trong mã nguồn (Test Suite)</div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; font-size: 13px;">
                        <div style="background: var(--canvas-alt); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--hairline);">
                            <code style="color: var(--primary-deep); font-weight: 600;">test_retrieval_eval.py</code><br>
                            <span style="color: var(--body); margin-top: 4px; display: block;">Kiểm tra độ chính xác của thứ hạng tìm kiếm và độ bao phủ từ khóa của hệ thống RAG.</span>
                        </div>
                        <div style="background: var(--canvas-alt); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--hairline);">
                            <code style="color: var(--primary-deep); font-weight: 600;">test_matrix_extraction.py</code><br>
                            <span style="color: var(--body); margin-top: 4px; display: block;">Kiểm tra tính toàn vẹn của JSON trả về, đảm bảo không bị lỗi format khi bóc dữ liệu.</span>
                        </div>
                        <div style="background: var(--canvas-alt); padding: 12px 14px; border-radius: 8px; border: 1px solid var(--hairline);">
                            <code style="color: var(--primary-deep); font-weight: 600;">test_report_citation_helpers.py</code><br>
                            <span style="color: var(--body); margin-top: 4px; display: block;">Kiểm tra thuật toán đối soát từng câu trong báo cáo với database trước khi trả về.</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">07 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 8: LIMITATIONS & ROADMAP ================= -->
        <section class="slide section-alt" id="slide-8">
            <div class="slide-content">
                <div class="pill-badge pill-primary">07 · HẠN CHẾ VÀ HƯỚNG CẢI TIẾN</div>
                <h2 class="section-title">Những Điểm Chưa Tốt Và Hướng Xử Lý Tiếp Theo</h2>
                <p class="subtitle">Nhìn nhận thẳng thắn các giới hạn của hệ thống hiện tại để có phương án nâng cấp rõ ràng.</p>

                <table class="custom-table">
                    <thead>
                        <tr>
                            <th style="width: 25%;">Giới hạn hiện tại</th>
                            <th style="width: 38%;">Vấn đề gặp phải trong thực tế</th>
                            <th style="width: 37%;">Hướng giải quyết kỹ thuật</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><strong>1. Đọc bảng số liệu và biểu đồ phức tạp</strong></td>
                            <td>Các thư viện bóc tách text hiện nay hay làm vỡ cấu trúc hàng/cột của các bảng thử nghiệm nhiều tầng, hoặc bỏ qua hoàn toàn biểu đồ kết quả.</td>
                            <td>
                                <strong>Tích hợp Vision-Language Model (VLM):</strong> Ứng dụng các mô hình như ColPali hoặc Docling OCR nâng cao để đọc trực tiếp hình ảnh trang tài liệu.
                            </td>
                        </tr>
                        <tr>
                            <td><strong>2. Tìm kiếm Vector chưa hiểu được mạng lưới quan hệ</strong></td>
                            <td>Vector search chỉ tìm theo độ tương đồng chữ nghĩa, không biết bài báo này trích dẫn bài báo nào khác hay phát triển từ trường phái nào.</td>
                            <td>
                                <strong>Nâng cấp lên GraphRAG:</strong> Dựng đồ thị tri thức (Knowledge Graph) liên kết Tác giả → Phương pháp → Bộ dữ liệu, giúp suy luận đa bước.
                            </td>
                        </tr>
                        <tr>
                            <td><strong>3. Đánh giá mâu thuẫn phụ thuộc vào một LLM</strong></td>
                            <td>Khi nhờ một mô hình duy nhất nhận định điểm bất đồng giữa các công trình, câu trả lời dễ bị ảnh hưởng bởi cách đặt câu hỏi ban đầu.</td>
                            <td>
                                <strong>Mô hình Multi-Agent Debate:</strong> Cho 2 agent đóng vai "ủng hộ" và "phản biện" tranh luận chéo trước khi đưa ra bản tổng hợp khách quan.
                            </td>
                        </tr>
                    </tbody>
                </table>

                <div class="card" style="margin-top: 18px; background: #ffffff; padding: 12px 18px;">
                    <p style="font-size: 13px; color: var(--charcoal);">
                        <em>Ghi chú:</em> Phần cấu trúc dữ liệu cho GraphRAG đã được thiết kế sẵn bước đầu trong tệp <code>app/services/knowledge_graph.py</code> của dự án.
                    </p>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">08 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 9: KEY LEARNINGS ================= -->
        <section class="slide" id="slide-9">
            <div class="slide-content">
                <div class="pill-badge pill-primary">08 · BÀI HỌC KỸ THUẬT</div>
                <h2 class="section-title">Những Điều Rút Ra Khi Trực Tiếp Xây Dựng AI Agent</h2>
                <p class="subtitle">Kinh nghiệm thực tế khi đưa một ý tưởng AI trên giấy thành một sản phẩm chạy ổn định.</p>

                <div class="grid-3">
                    <div class="card">
                        <div class="stat-badge" style="font-size: 26px; margin-bottom: 6px;">01. Kiểm soát luồng</div>
                        <div class="card-title" style="font-size: 16.5px;">Agent cần State Machine rõ ràng</div>
                        <p class="card-text">
                            Các luồng Agent tự do rất dễ rơi vào tình trạng lặp vô tận hoặc gọi công cụ sai mục đích khi gặp dữ liệu lạ. Việc dùng LangGraph để giới hạn số bước, quy định rõ điều kiện dừng và có nhánh xử lý khi công cụ lỗi là yếu tố bắt buộc nếu muốn chạy thật.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="font-size: 26px; margin-bottom: 6px;">02. Trải nghiệm chờ</div>
                        <div class="card-title" style="font-size: 16.5px;">Phải cho người dùng thấy AI đang làm gì</div>
                        <p class="card-text">
                            Một tác vụ Agent đọc hàng chục bài báo có thể kéo dài gần 1 phút. Nếu chỉ để vòng xoay loading, người dùng sẽ tắt trang vì nghĩ hệ thống bị treo. Dùng Server-Sent Events (SSE) để truyền từng bước: <em>"Đang đọc bài A"</em>, <em>"Đang bóc ma trận bài B"</em> tạo cảm giác yên tâm và chuyên nghiệp.
                        </p>
                    </div>

                    <div class="card">
                        <div class="stat-badge" style="font-size: 26px; margin-bottom: 6px;">03. Chất lượng dữ liệu</div>
                        <div class="card-title" style="font-size: 16.5px;">Làm sạch dữ liệu quan trọng hơn đổi model to</div>
                        <p class="card-text">
                            Dành thời gian chỉnh sửa parser PDF, cắt đoạn hợp lý và khử trùng lặp mang lại độ chính xác cao hơn rất nhiều so với việc cố dùng một model lớn hơn. Dữ liệu đầu vào sạch giúp model tầm trung chạy vừa nhanh vừa rẻ hơn tới 80%.
                        </p>
                    </div>
                </div>

                <div class="card" style="margin-top: 22px; background: var(--canvas-alt); border-color: var(--hairline); padding: 16px 20px;">
                    <p style="font-size: 14px; color: var(--ink); line-height: 1.5;">
                        <strong>Góc nhìn của em:</strong> Trọng tâm của một kỹ sư AI Agent không nằm ở việc viết những câu prompt hoa mỹ, mà là hiểu rõ bản chất dữ liệu, thiết kế luồng kiểm soát lỗi chặt chẽ và tối ưu chi phí vận hành cho từng token.
                    </p>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand">LUMEN · AI AGENT</span>
                <span class="num">09 / 10</span>
            </div>
        </section>

        <!-- ================= SLIDE 10: DEMO & CONCLUSION ================= -->
        <section class="slide hero-slide" id="slide-10">
            <div class="hero-mesh"></div>
            <div class="slide-content">
                <div class="pill-badge pill-primary">TỔNG KẾT &amp; TRAO ĐỔI KỸ THUẬT</div>
                <h1 class="hero-title" style="font-size: 76px; margin-bottom: 14px;">LUMEN<span class="logo-dot">.</span></h1>
                <p class="hero-sub" style="font-size: 22px; max-width: 900px; margin-bottom: 32px;">
                    Mã nguồn, kịch bản kiểm thử tự động và video mô phỏng hệ thống đã sẵn sàng chia sẻ.
                </p>

                <div class="grid-3" style="max-width: 1100px; z-index: 2; position: relative;">
                    <div class="hero-meta-card">
                        <div class="label">VIDEO TRÌNH DIỄN THỰC TẾ</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px;">
                            <a href="https://youtu.be/uNt316BZaY8" target="_blank" style="color: var(--primary); text-decoration: underline;">
                                Xem Video Demo Trên YouTube ↗
                            </a>
                        </div>
                        <p style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Xem trực tiếp luồng tìm kiếm, tạo ma trận và viết báo cáo</p>
                    </div>

                    <div class="hero-meta-card">
                        <div class="label">MÃ NGUỒN &amp; TÀI LIỆU</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px;">
                            <a href="https://github.com/vietlinhh02" target="_blank" style="color: var(--primary); text-decoration: underline;">
                                Kho lưu trữ GitHub Repository ↗
                            </a>
                        </div>
                        <p style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">FastAPI Backend + Next.js 16 + 50+ Test Cases</p>
                    </div>

                    <div class="hero-meta-card">
                        <div class="label">SẴN SÀNG PHẢN BIỆN</div>
                        <div class="val" style="font-size: 14px; margin-top: 6px; color: var(--ink);">
                            Trao đổi kỹ thuật chuyên sâu
                        </div>
                        <p style="font-size: 12px; color: var(--charcoal); margin-top: 4px;">Sẵn sàng thảo luận về luồng code và giải pháp tối ưu hệ thống</p>
                    </div>
                </div>
            </div>
            <div class="slide-footer">
                <span class="brand"></span>
                <span class="num">10 / 10</span>
            </div>
        </section>

    </main>

    <script>
        const container = document.getElementById('deck-container');
        const slides = document.querySelectorAll('.slide');
        const indicator = document.getElementById('slide-indicator');
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

html_final = html_template.replace("__IMG_MATRIX__", encoded.get('matrix.png', ''))

output_path = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/pitch_materials/lumen_pixta_presentation.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_final)

print(f"Generated pure-content light-mode presentation successfully: {output_path}")
print(f"Size: {os.path.getsize(output_path)} bytes")
