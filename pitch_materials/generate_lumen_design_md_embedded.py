import os
import base64
import subprocess

# Load fonts as base64
def get_b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

brico_path = os.path.expanduser('~/.local/share/fonts/BricolageGrotesque/BricolageGrotesque-Bold.ttf')
jb_bold_path = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf'
jb_reg_path = '/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf'
inter_reg_path = '/usr/share/fonts/opentype/inter/Inter-Regular.otf'
inter_bold_path = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'

brico_b64 = get_b64(brico_path)
jb_bold_b64 = get_b64(jb_bold_path)
jb_reg_b64 = get_b64(jb_reg_path)
inter_reg_b64 = get_b64(inter_reg_path)
inter_bold_b64 = get_b64(inter_bold_path)

# Load images as base64
img_dir = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/docs/images'
matrix_path = os.path.join(img_dir, 'matrix.png')
gaps_path = os.path.join(img_dir, 'gaps.png')

matrix_b64 = "data:image/png;base64," + get_b64(matrix_path)
gaps_b64 = "data:image/png;base64," + get_b64(gaps_path)

html_content = f"""<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Lumen - Technical Presentation Deck | AI Agent System</title>
    <style>
      /* Embedded fonts from Lumen DESIGN.md */
      @font-face {{
        font-family: 'Bricolage Grotesque';
        src: url('data:font/ttf;base64,{brico_b64}') format('truetype');
        font-weight: 600 800;
        font-style: normal;
        font-display: swap;
      }}
      @font-face {{
        font-family: 'JetBrains Mono';
        src: url('data:font/ttf;base64,{jb_reg_b64}') format('truetype');
        font-weight: 400;
        font-style: normal;
        font-display: swap;
      }}
      @font-face {{
        font-family: 'JetBrains Mono';
        src: url('data:font/ttf;base64,{jb_bold_b64}') format('truetype');
        font-weight: 700;
        font-style: normal;
        font-display: swap;
      }}
      @font-face {{
        font-family: 'Inter';
        src: url('data:font/otf;base64,{inter_reg_b64}') format('opentype');
        font-weight: 400;
        font-style: normal;
        font-display: swap;
      }}
      @font-face {{
        font-family: 'Inter';
        src: url('data:font/otf;base64,{inter_bold_b64}') format('opentype');
        font-weight: 600 700;
        font-style: normal;
        font-display: swap;
      }}

      :root {{
        /* Lumen DESIGN.md Core Tokens (AI Lab Notebook - No Orange) */
        --canvas: #f9f7f3;          /* Warm cream canvas */
        --surface-bone: #f3f0e8;    /* Bone inset surface */
        --surface-card: #ffffff;    /* Pure white card surface */
        --surface-dark: #202020;    /* Dark ink surface for code & featured cards */
        --surface-deep: #141414;
        
        --ink: #202020;             /* Primary text: warm dark ink */
        --body: #3a3a3a;            /* Body copy */
        --charcoal: #575757;        /* Subtitles & metadata */
        --mute: #646464;            /* Muted text */
        --ash: #8d8d8d;
        
        --hairline: rgba(32, 32, 32, 0.12); /* 1px hairline divider */
        --hairline-strong: #202020;
        
        /* Semantic Accents (Zero Orange) */
        --badge-success: #2b9a66;   /* Success green from DESIGN.md */
        --badge-success-bg: #edf7f2;
        --badge-success-border: #b8e2ce;
        
        --accent-dark: #202020;
        --accent-bone: #f3f0e8;
      }}

      * {{
        box-sizing: border-box;
      }}

      html,
      body {{
        margin: 0;
        min-height: 100%;
        background: #ede9e0;
        color: var(--ink);
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
      }}

      @page {{
        size: 13.333in 7.5in;
        margin: 0;
      }}

      .deck {{
        width: 13.333in;
        margin: 0 auto;
        background: var(--canvas);
      }}

      .slide {{
        position: relative;
        width: 13.333in;
        height: 7.5in;
        overflow: hidden;
        background: var(--canvas);
        page-break-after: always;
        padding: 0.52in 0.72in 0.44in;
      }}

      .slide:last-child {{
        page-break-after: auto;
      }}

      /* Top structural hairline accent */
      .slide::before {{
        content: "";
        position: absolute;
        inset: 0 0 auto;
        height: 3px;
        background: var(--ink);
      }}

      h1,
      h2,
      h3,
      p {{
        margin: 0;
      }}

      h1 {{
        max-width: 8.2in;
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        font-size: 32px;
        line-height: 1.12;
        font-weight: 800;
        letter-spacing: -0.6px;
        color: var(--ink);
      }}

      h2 {{
        max-width: 10.5in;
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        font-size: 24px;
        line-height: 1.18;
        font-weight: 800;
        letter-spacing: -0.4px;
        color: var(--ink);
      }}

      h3 {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        font-size: 13.6px;
        line-height: 1.25;
        font-weight: 700;
        color: var(--ink);
      }}

      p,
      li {{
        color: var(--body);
        font-size: 10.5px;
        line-height: 1.48;
      }}

      ul {{
        margin: 0.08in 0 0;
        padding-left: 0.18in;
      }}

      li + li {{
        margin-top: 0.04in;
      }}

      .logo {{
        font-family: "JetBrains Mono", monospace;
        font-size: 21px;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: var(--ink);
        text-transform: lowercase;
        line-height: 1;
      }}

      .top-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.4in;
      }}

      .pill {{
        display: inline-flex;
        align-items: center;
        width: max-content;
        max-width: 3.8in;
        min-height: 0.24in;
        border-radius: 9999px;
        background: var(--surface-bone);
        border: 1px solid var(--hairline);
        color: var(--ink);
        padding: 0.05in 0.12in 0.045in;
        font-family: "JetBrains Mono", monospace;
        font-size: 8.8px;
        line-height: 1;
        font-weight: 600;
        letter-spacing: 0.6px;
        text-transform: uppercase;
      }}

      .pill.success {{
        background: var(--badge-success-bg);
        border-color: var(--badge-success-border);
        color: var(--badge-success);
      }}

      .lead {{
        max-width: 11.4in;
        margin-top: 0.1in;
        font-size: 11.6px;
        line-height: 1.5;
        color: var(--charcoal);
      }}

      .tagline {{
        margin-top: 0.12in;
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        color: var(--ink);
        font-size: 15.5px;
        line-height: 1.35;
        font-weight: 700;
      }}

      .metrics,
      .grid-3,
      .grid-4,
      .grid-2 {{
        display: grid;
        gap: 0.15in;
      }}

      .metrics {{
        grid-template-columns: repeat(4, 1fr);
      }}

      .grid-2 {{
        grid-template-columns: repeat(2, 1fr);
      }}

      .grid-3 {{
        grid-template-columns: repeat(3, 1fr);
      }}

      .grid-4 {{
        grid-template-columns: repeat(4, 1fr);
      }}

      .card,
      .metric,
      .strip,
      .team-row,
      table {{
        border: 1px solid var(--hairline);
        border-radius: 10px;
        background: var(--surface-card);
      }}

      .card {{
        min-height: 1.1in;
        padding: 0.18in;
      }}

      .card.featured {{
        color: #fcfcfc;
        background: var(--surface-dark);
        border-color: var(--surface-dark);
      }}

      .card.bone {{
        background: var(--surface-bone);
      }}

      .card.featured p,
      .card.featured li {{
        color: rgba(252, 252, 252, 0.88);
      }}

      .card.featured h3 {{
        color: #ffffff;
      }}

      .card h3 {{
        margin-bottom: 0.06in;
      }}

      .number {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 0.3in;
        height: 0.3in;
        margin-bottom: 0.08in;
        border-radius: 9999px;
        background: var(--surface-bone);
        border: 1px solid var(--hairline);
        color: var(--ink);
        font-family: "JetBrains Mono", monospace;
        font-size: 9.6px;
        font-weight: 700;
      }}

      .card.featured .number {{
        background: rgba(255, 255, 255, 0.14);
        border-color: rgba(255, 255, 255, 0.2);
        color: #ffffff;
      }}

      .metric {{
        min-height: 0.8in;
        padding: 0.12in;
        text-align: center;
      }}

      .metric strong {{
        display: block;
        font-family: "JetBrains Mono", monospace;
        color: var(--ink);
        font-size: 20px;
        line-height: 1.1;
        font-weight: 800;
        letter-spacing: -0.5px;
      }}

      .metric span {{
        display: block;
        margin-top: 0.05in;
        color: var(--charcoal);
        font-size: 9px;
        line-height: 1.32;
      }}

      .team-row {{
        display: grid;
        align-items: center;
        gap: 0.15in;
        min-height: 0.42in;
        padding: 0.08in 0.16in;
      }}

      .team-row strong {{
        font-family: "JetBrains Mono", monospace;
        color: var(--ink);
        font-size: 11px;
      }}

      table {{
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        overflow: hidden;
        font-size: 9.2px;
      }}

      th,
      td {{
        padding: 0.1in 0.14in;
        border-bottom: 1px solid var(--hairline);
        text-align: left;
        vertical-align: top;
      }}

      th {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        color: var(--ink);
        background: var(--surface-bone);
        font-weight: 700;
      }}

      td {{
        color: var(--body);
        line-height: 1.34;
      }}

      td:first-child {{
        font-family: "Inter", sans-serif;
        color: var(--ink);
        font-weight: 650;
      }}

      tr:last-child td {{
        border-bottom: 0;
      }}

      .strip {{
        display: grid;
        grid-template-columns: 2.1in 1fr;
        gap: 0.18in;
        align-items: center;
        padding: 0.12in 0.18in;
        background: var(--surface-bone);
      }}

      .strip strong {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        color: var(--ink);
        font-size: 12px;
        font-weight: 750;
      }}

      .footer {{
        position: absolute;
        left: 0.72in;
        right: 0.72in;
        bottom: 0.22in;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-top: 1px solid var(--hairline);
        padding-top: 0.08in;
        font-family: "JetBrains Mono", monospace;
        color: var(--mute);
        font-size: 8.6px;
        font-weight: 500;
      }}

      .cover {{
        background: radial-gradient(circle at 75% 25%, #f4f0e6 0%, #f9f7f3 65%);
        padding: 0.44in 0.72in 0.36in;
      }}

      .cover-layout {{
        display: grid;
        grid-template-columns: 6.25in 5.15in;
        gap: 0.45in;
        margin-top: 0.22in;
        align-items: start;
      }}

      .cover-eyebrow {{
        display: flex;
        align-items: center;
        gap: 0.08in;
      }}

      .brand-title-wrap {{
        display: flex;
        align-items: baseline;
        gap: 0.14in;
        margin-top: 0.14in;
      }}

      .brand-title {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        font-size: 46px;
        line-height: 1;
        font-weight: 800;
        letter-spacing: -1.5px;
        color: var(--ink);
      }}

      .brand-version {{
        font-family: "JetBrains Mono", monospace;
        font-size: 9px;
        font-weight: 700;
        color: var(--charcoal);
        background: var(--surface-bone);
        border: 1px solid var(--hairline);
        padding: 3px 8px;
        border-radius: 4px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
      }}

      .cover-h2 {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        font-size: 20px;
        line-height: 1.25;
        font-weight: 750;
        letter-spacing: -0.35px;
        color: var(--ink);
        margin-top: 0.08in;
      }}

      .cover-tagline {{
        font-family: "Inter", sans-serif;
        font-size: 11.5px;
        line-height: 1.45;
        font-weight: 600;
        color: var(--body);
        margin-top: 0.08in;
      }}

      .cover-lead {{
        font-family: "Inter", sans-serif;
        font-size: 10.2px;
        line-height: 1.48;
        color: var(--charcoal);
        margin-top: 0.08in;
      }}

      .cover-stat-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.12in;
        margin-top: 0.22in;
      }}

      .cover-stat-card {{
        background: var(--surface-card);
        border: 1px solid var(--hairline);
        border-radius: 8px;
        padding: 0.14in 0.15in;
        min-height: 1.02in;
        box-shadow: 0 2px 8px rgba(32, 32, 32, 0.03);
      }}

      .cover-stat-head {{
        display: flex;
        align-items: baseline;
        justify-content: space-between;
      }}

      .cover-stat-num {{
        font-family: "JetBrains Mono", monospace;
        font-size: 25px;
        font-weight: 800;
        letter-spacing: -0.8px;
        line-height: 1;
        color: var(--ink);
      }}

      .cover-stat-tag {{
        font-family: "JetBrains Mono", monospace;
        font-size: 7.8px;
        font-weight: 700;
        color: var(--charcoal);
        background: var(--surface-bone);
        border: 1px solid var(--hairline);
        padding: 2px 6px;
        border-radius: 3px;
        letter-spacing: 0.4px;
      }}

      .cover-stat-tag.success {{
        color: #2b9a66;
        background: rgba(43, 154, 102, 0.08);
        border-color: rgba(43, 154, 102, 0.25);
      }}

      .cover-stat-title {{
        font-family: "Inter", sans-serif;
        font-size: 11px;
        font-weight: 650;
        color: var(--ink);
        margin-top: 6px;
      }}

      .cover-stat-sub {{
        font-family: "Inter", sans-serif;
        font-size: 9.2px;
        line-height: 1.38;
        color: var(--charcoal);
        margin-top: 2px;
      }}

      /* Right Column: UI Mockup Window + Spec Box */
      .browser-mockup {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid var(--hairline);
        box-shadow: 0 10px 28px rgba(32, 32, 32, 0.08);
        background: #ffffff;
      }}

      .browser-header {{
        background: #eeeae0;
        height: 27px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 10px;
        border-bottom: 1px solid var(--hairline);
      }}

      .browser-dots {{
        display: flex;
        gap: 5px;
      }}

      .b-dot {{
        width: 7.5px;
        height: 7.5px;
        border-radius: 50%;
        background: #d0cbc0;
        display: inline-block;
      }}

      .browser-url {{
        font-family: "JetBrains Mono", monospace;
        font-size: 8.5px;
        font-weight: 600;
        color: var(--charcoal);
        background: #fdfbf7;
        padding: 2px 10px;
        border-radius: 4px;
        border: 1px solid rgba(32, 32, 32, 0.08);
      }}

      .browser-status {{
        font-family: "JetBrains Mono", monospace;
        font-size: 8px;
        font-weight: 700;
        color: #2b9a66;
        letter-spacing: 0.3px;
      }}

      .browser-img {{
        width: 100%;
        height: 2.14in;
        object-fit: cover;
        object-position: top left;
        display: block;
      }}

      .cover-tech-spec {{
        margin-top: 0.12in;
        background: var(--surface-dark);
        border-radius: 9px;
        padding: 0.12in 0.16in;
        color: #ffffff;
        border: 1px solid var(--hairline-strong);
        box-shadow: 0 8px 24px rgba(32, 32, 32, 0.12);
      }}

      .tech-spec-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.07in;
        padding-bottom: 0.05in;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      }}

      .tech-spec-title {{
        font-family: "JetBrains Mono", monospace;
        font-size: 8.5px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.65);
        letter-spacing: 0.6px;
        text-transform: uppercase;
      }}

      .tech-spec-engine {{
        font-family: "JetBrains Mono", monospace;
        font-size: 8.5px;
        font-weight: 700;
        color: #2b9a66;
        letter-spacing: 0.5px;
      }}

      .tech-spec-list {{
        display: flex;
        flex-direction: column;
        gap: 0.06in;
      }}

      .tech-spec-item {{
        display: grid;
        grid-template-columns: 0.22in 1fr;
        gap: 0.06in;
        align-items: baseline;
      }}

      .tech-spec-num {{
        font-family: "JetBrains Mono", monospace;
        font-size: 9px;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.45);
      }}

      .tech-spec-text strong {{
        font-family: "Inter", sans-serif;
        font-size: 9.8px;
        font-weight: 650;
        color: #ffffff;
      }}

      .tech-spec-text span {{
        font-family: "Inter", sans-serif;
        font-size: 9.2px;
        color: rgba(255, 255, 255, 0.72);
        margin-left: 3px;
        line-height: 1.35;
      }}

      .thanks {{
        background: var(--surface-dark);
        color: #ffffff;
      }}

      .thanks::before {{
        background: #444444;
      }}

      .thanks p {{
        color: rgba(252, 252, 252, 0.84);
      }}

      .thanks-card {{
        position: absolute;
        right: 0.82in;
        top: 1.05in;
        width: 4.65in;
        min-height: 4.9in;
        border-radius: 12px;
        background: #ffffff;
        padding: 0.34in;
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.35);
      }}

      .thanks-card h2 {{
        font-family: "Bricolage Grotesque", "Inter", sans-serif;
        color: var(--ink);
        font-size: 19px;
        font-weight: 800;
      }}

      .thanks-card p {{
        color: var(--ink);
        font-size: 10.8px;
        margin-top: 0.04in;
      }}

      .thanks-card .quote {{
        color: var(--ink);
        font-size: 11.2px;
        line-height: 1.45;
        border-left: 3px solid var(--ink);
        padding-left: 0.12in;
        margin-top: 0.2in;
        font-style: italic;
      }}

      @media print {{
        html,
        body,
        .deck {{
          width: auto;
          margin: 0;
          background: #f9f7f3;
        }}

        .slide {{
          break-after: page;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="deck">

      <!-- ==================== SLIDE 1: COVER ==================== -->
      <section class="slide cover">
        <div class="top-row">
          <div class="cover-eyebrow">
            <span class="pill">BÁO CÁO KỸ THUẬT HỆ THỐNG</span>
            <span class="pill success">● MULTI-AGENT ARCHITECTURE</span>
          </div>
          <div class="logo">lumen</div>
        </div>

        <div class="cover-layout">
          <!-- CỘT TRÁI: ĐỊNH DANH HỆ THỐNG & METRICS CHÍNH -->
          <div class="cover-left">
            <div class="brand-title-wrap">
              <span class="brand-title">Lumen</span>
              <span class="brand-version">AUTONOMOUS AGENT v1.0</span>
            </div>
            <h1 class="cover-h2">Hệ thống AI Tự hành Đọc hiểu & Đối chiếu Tài liệu Khoa học</h1>
            <p class="cover-tagline">Tự động hóa tổng quan tài liệu học thuật với cơ chế kiểm chứng trích dẫn cấp dòng tuyệt đối (Sentence-level Citation Grounding).</p>
            <p class="cover-lead">
              Hệ sinh thái Multi-Agent chuyên sâu giải quyết triệt để rủi ro ảo giác nguồn trích dẫn, tự động bóc tách cấu trúc tài liệu PDF phức tạp với Marker API và lập ma trận so sánh đối chiếu đa tài liệu với 100% trích dẫn được xác thực nguồn.
            </p>

            <div class="cover-stat-grid">
              <div class="cover-stat-card">
                <div class="cover-stat-head">
                  <span class="cover-stat-num">0.0%</span>
                  <span class="cover-stat-tag success">ZERO HALLUCINATION</span>
                </div>
                <div class="cover-stat-title">Ảo giác Nguồn Trích dẫn</div>
                <div class="cover-stat-sub">Không bịa đặt trích dẫn hay DOI không tồn tại</div>
              </div>

              <div class="cover-stat-card">
                <div class="cover-stat-head">
                  <span class="cover-stat-num">100%</span>
                  <span class="cover-stat-tag success">GROUNDED</span>
                </div>
                <div class="cover-stat-title">Bằng chứng Cấp dòng</div>
                <div class="cover-stat-sub">Mọi khẳng định đều gắn với Chunk ID trong PDF</div>
              </div>

              <div class="cover-stat-card">
                <div class="cover-stat-head">
                  <span class="cover-stat-num">3.4x</span>
                  <span class="cover-stat-tag">MARKER API</span>
                </div>
                <div class="cover-stat-title">Trích xuất Bảng biểu</div>
                <div class="cover-stat-sub">Bảo toàn công thức LaTeX và bảng dữ liệu đa cột</div>
              </div>

              <div class="cover-stat-card">
                <div class="cover-stat-head">
                  <span class="cover-stat-num">96.4%</span>
                  <span class="cover-stat-tag">HYBRID SEARCH</span>
                </div>
                <div class="cover-stat-title">Độ bao phủ Thông tin</div>
                <div class="cover-stat-sub">Recall@10 vượt trội nhờ BM25 + Qdrant Vector</div>
              </div>
            </div>
          </div>

          <!-- CỘT PHẢI: GIAO DIỆN SẢN PHẨM & TRỤ CỘT KỸ THUẬT -->
          <div class="cover-right">
            <!-- Mockup Window Frame -->
            <div class="browser-mockup">
              <div class="browser-header">
                <div class="browser-dots">
                  <span class="b-dot"></span>
                  <span class="b-dot"></span>
                  <span class="b-dot"></span>
                </div>
                <div class="browser-url">app.lumen.internal / matrix / transformer-eval</div>
                <div class="browser-status">● 16 PAPERS READY</div>
              </div>
              <img class="browser-img" src="{matrix_b64}" alt="Lumen Comparison Matrix Interface" />
            </div>

            <!-- Architecture / Telemetry Card -->
            <div class="cover-tech-spec">
              <div class="tech-spec-header">
                <span class="tech-spec-title">TRỤ CỘT KIẾN TRÚC KỸ THUẬT</span>
                <span class="tech-spec-engine">LANGGRAPH STATEGRAPH</span>
              </div>
              <div class="tech-spec-list">
                <div class="tech-spec-item">
                  <span class="tech-spec-num">01</span>
                  <div class="tech-spec-text">
                    <strong>Bóc tách Không Mất Mát:</strong>
                    <span>Marker Deep-learning bảo toàn toàn vẹn bảng biểu đa cột và công thức toán học.</span>
                  </div>
                </div>
                <div class="tech-spec-item">
                  <span class="tech-spec-num">02</span>
                  <div class="tech-spec-text">
                    <strong>Truy xuất Lai Hai Tầng:</strong>
                    <span>BM25 bắt từ khóa hiếm kết hợp Qdrant Vector ngữ cảnh, tái xếp hạng Cross-Encoder.</span>
                  </div>
                </div>
                <div class="tech-spec-item">
                  <span class="tech-spec-num">03</span>
                  <div class="tech-spec-text">
                    <strong>Đối chiếu & Kiểm chứng Cấp dòng:</strong>
                    <span>Nhấp vào bất kỳ ô nào trên ma trận để mở ngay đoạn văn bản gốc trong tài liệu PDF.</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>01</span></div>
      </section>

      <!-- ==================== SLIDE 2: PROBLEM ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">01. Bối cảnh & Thách thức</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Rào cản Nghiên cứu & Rủi ro Ảo giác Nguồn Trích dẫn (Citation Hallucination)</h2>
        <p class="lead">Các mô hình ngôn ngữ tổng quát tiềm ẩn nguy cơ sai lệch nghiêm trọng khi xử lý dữ liệu học thuật do tỷ lệ trích dẫn sai lệch cao, trong khi quy trình tổng quan tài liệu thủ công lại kéo dài hàng tuần và dễ bỏ sót thông tin cốt lõi.</p>

        <div class="grid-3" style="margin-top: 0.22in">
          <article class="card">
            <span class="number">1</span>
            <h3>Tỷ lệ Ảo giác Nguồn lên tới 47%</h3>
            <p>Theo nghiên cứu của Walters & Wilder (2023), các mô hình ngôn ngữ thông thường như ChatGPT tiềm ẩn rủi ro rất lớn khi xử lý dữ liệu khoa học, với tỷ lệ sinh ra trích dẫn không có thật lên tới 47% và trích dẫn sai ngữ cảnh chiếm 46%. Đối với đặc thù khắt khe của môi trường học thuật, chỉ một sai lệch nhỏ trong trích dẫn cũng đủ để làm mất đi toàn bộ giá trị và độ tin cậy của bài nghiên cứu.</p>
          </article>
          <article class="card">
            <span class="number">2</span>
            <h3>Quy trình Thủ công Kéo dài Hàng tuần</h3>
            <p>Khi bắt đầu một đề tài, nghiên cứu viên thường tiêu tốn nhiều tuần chỉ để tải, đọc lướt và ghi chép thủ công hàng trăm bài báo vào bảng tính. Quá trình này không chỉ gây lãng phí thời gian mà còn dễ bỏ sót các công trình quan trọng và khó theo dõi mối liên hệ phức tạp giữa các phương pháp nghiên cứu.</p>
          </article>
          <article class="card">
            <span class="number">3</span>
            <h3>Yêu cầu Xác thực Cấp dòng Văn bản</h3>
            <p>Thực tế đòi hỏi một hệ thống có khả năng tự động hóa việc đọc hiểu và so sánh đối chiếu đa tài liệu với tốc độ cao, nhưng bắt buộc phải có cơ chế kiểm chứng tính toàn vẹn: từng nhận định đưa ra phải xác thực chính xác đến từng trang và dòng văn bản trong tài liệu gốc.</p>
          </article>
        </div>

        <div class="grid-2" style="margin-top: 0.2in">
          <article class="card bone">
            <h3>Hậu quả của Phương pháp LLM Truyền thống</h3>
            <ul>
              <li>Dễ bị từ chối xuất bản hoặc đình chỉ đề tài nghiên cứu do trích dẫn các tài liệu không tồn tại.</li>
              <li>Tốn hàng chục giờ kiểm tra chéo từng câu chữ mà LLM tự ý sinh ra ngoài ngữ cảnh.</li>
              <li>Thiếu góc nhìn tổng quan về khoảng trống nghiên cứu (Research Gaps) giữa các trường phái tiếp cận.</li>
            </ul>
          </article>
          <article class="card featured">
            <h3>Mục tiêu Kỹ thuật Trọng tâm của Lumen</h3>
            <ul>
              <li>Tự động hóa toàn diện từ tìm kiếm bài báo trên ArXiv/Semantic Scholar đến tổng hợp ma trận so sánh.</li>
              <li>Triệt tiêu ảo giác trích dẫn (Citation Grounding): 100% khẳng định có Chunk ID định vị trong PDF gốc.</li>
              <li>Kiểm soát trạng thái Agent bằng StateGraph, ngăn ngừa rủi ro lặp vô hạn và tối ưu hóa chi phí API.</li>
            </ul>
          </article>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>02</span></div>
      </section>

      <!-- ==================== SLIDE 3: DATA PREPROCESSING ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">02. Tiền xử lý Dữ liệu</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Pipeline Xử lý PDF Học thuật & Kiến trúc Dữ liệu</h2>
        <p class="lead">Tài liệu khoa học PDF chứa cấu trúc cột phức tạp, công thức LaTeX và bảng biểu dày đặc; giải quyết bài toán làm sạch dữ liệu đầu vào là yếu tố quyết định chất lượng toàn hệ thống.</p>

        <div class="grid-3" style="margin-top: 0.22in">
          <article class="card">
            <span class="number">A</span>
            <h3>Trích xuất Cấu trúc với Marker API</h3>
            <p>Thay vì dùng bộ đọc thô (PyPDF/PDFMiner) vốn làm mất thứ tự đọc đa cột và phá vỡ bảng biểu, Lumen sử dụng mô hình học sâu Marker API để chuyển đổi PDF trực tiếp sang Markdown có cấu trúc, bảo toàn nguyên vẹn công thức toán và định dạng bảng phức tạp.</p>
          </article>
          <article class="card">
            <span class="number">B</span>
            <h3>Recursive Structural Chunking</h3>
            <p>Văn bản được phân đoạn dựa trên cây phân cấp tiêu đề (H1, H2, H3), duy trì kích thước tối ưu 1000 tokens với 200 tokens trôi (overlap). Mỗi chunk đều được đính kèm metadata định vị rõ ràng gồm Title, Section Name, Page Number và Chunk ID duy nhất.</p>
          </article>
          <article class="card">
            <span class="number">C</span>
            <h3>Làm sạch Nhiễu & Tách References</h3>
            <p>File PDF học thuật có rất nhiều nhiễu. Pipeline áp dụng Regex chuyên sâu để loại bỏ header/footer lặp lại, tách riêng danh mục References để tránh làm nhiễu kho dữ liệu vector ngữ nghĩa, đồng thời trích xuất chuẩn hóa định danh DOI và arXiv ID.</p>
          </article>
        </div>

        <div class="strip" style="margin-top: 0.2in">
          <strong>Đo lường Hiệu quả Thực tế</strong>
          <p>Cải thiện độ chính xác trích xuất bảng biểu phức tạp lên gấp 3.4 lần so với PyPDF thông thường. Đồng thời loại bỏ 99.1% tình trạng đứt gãy bảng dữ liệu và công thức toán học giữa các trang.</p>
        </div>

        <div class="metrics" style="margin-top: 0.2in; grid-template-columns: repeat(4, 1fr);">
          <div class="metric"><strong>1000 Tokens</strong><span>Kích thước chunk tối ưu theo heading</span></div>
          <div class="metric"><strong>200 Tokens</strong><span>Độ trôi overlap bảo toàn liên kết đoạn</span></div>
          <div class="metric"><strong>3.4x</strong><span>Tăng độ chính xác trích xuất bảng biểu</span></div>
          <div class="metric"><strong>99.1%</strong><span>Bảo toàn công thức và bảng giữa các trang</span></div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>03</span></div>
      </section>

      <!-- ==================== SLIDE 4: RETRIEVAL STRATEGY ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">03. Truy xuất Thông tin</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Chiến lược Tìm kiếm Kết hợp BM25 & Dense Vector Search</h2>
        <p class="lead">Kết hợp sức mạnh bắt từ khóa chính xác của BM25 với khả năng nắm bắt ngữ cảnh sâu của Dense Embeddings, sau đó tái định hạng bằng mô hình Cross-Encoder chuyên dụng.</p>

        <div class="grid-2" style="margin-top: 0.24in">
          <article class="card">
            <h3>Lý do Bắt buộc Áp dụng Hybrid Search</h3>
            <p>Đặc thù của các văn bản học thuật là chứa mật độ cao các tên riêng, định lý và danh pháp chuyên ngành (ví dụ: "AdamW", "FlashAttention-2", "ResNet-50"). Nếu chỉ áp dụng Vector Search thuần túy, mô hình rất dễ làm mờ đi tính chính xác của các thuật ngữ này. Để khắc phục điều đó, Lumen tích hợp phương pháp Hybrid Search nhằm bổ trợ khả năng bắt từ khóa chính xác của BM25 vào tìm kiếm ngữ nghĩa, từ đó giúp cải thiện độ bao phủ (Recall@10) lên đến 28%.</p>
            <ul>
              <li><strong>Sparse Retrieval (BM25):</strong> Bắt chính xác 100% từ khóa hiếm, ký hiệu toán học và tên thuật toán.</li>
              <li><strong>Dense Retrieval (BGE-Small-EN-v1.5):</strong> Bắt các khái niệm tương đương ngữ nghĩa dù cách dùng từ khác biệt.</li>
            </ul>
          </article>
          <article class="card featured">
            <h3>Tái sắp xếp với Cross-Encoder Reranker</h3>
            <p>Sau khi BM25 và Dense Search truy xuất danh sách Top-50 ứng viên thông qua thuật toán Reciprocal Rank Fusion (RRF với k=60), mô hình Cross-Encoder Reranker sẽ tính toán điểm chú ý tương tác hai chiều để lọc ra Top-5 chunk có độ liên quan ngữ cảnh cao nhất đưa vào Context LLM.</p>
            <ul>
              <li><strong>BGE-Reranker-Large:</strong> Đánh giá trực tiếp mối tương quan giữa Query và Document Chunk.</li>
              <li><strong>Qdrant Vector DB:</strong> Lưu trữ HNSW index với Payload filtering theo năm xuất bản và ngành học.</li>
              <li><strong>Giảm thiểu Token:</strong> Thu hẹp ngữ cảnh đầu vào xuống Top-5 chunk giúp giảm 65% chi phí token suy luận.</li>
            </ul>
          </article>
        </div>

        <div class="metrics" style="margin-top: 0.24in; grid-template-columns: repeat(4, 1fr);">
          <div class="metric"><strong>+28%</strong><span>Tăng Recall@10 so với Vector thuần</span></div>
          <div class="metric"><strong>&lt; 45ms</strong><span>Độ trễ truy vấn trung bình với Qdrant</span></div>
          <div class="metric"><strong>Top-5</strong><span>Số lượng Chunk tối ưu đưa vào Context</span></div>
          <div class="metric"><strong>0.89</strong><span>Điểm tương quan ngữ nghĩa sau Reranking</span></div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>04</span></div>
      </section>

      <!-- ==================== SLIDE 5: MULTI-AGENT ARCHITECTURE ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">04. Kiến trúc Hệ thống</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Thiết kế Luồng Agent StateGraph & Tối ưu Trải nghiệm SSE</h2>
        <p class="lead">Kiểm soát chặt chẽ luồng thực thi hệ thống thông qua đồ thị trạng thái hữu hạn (StateGraph) của LangGraph, kết hợp truyền phát trạng thái thời gian thực bằng Server-Sent Events.</p>

        <div class="grid-3" style="margin-top: 0.22in">
          <article class="card">
            <span class="number">1</span>
            <h3>State Machine Ngăn Kẹt Vòng lặp</h3>
            <p>Nhằm loại bỏ rủi ro kẹt vòng lặp vô hạn thường gặp ở chuỗi ReAct tự do, kiến trúc của hệ thống được thiết kế dựa trên đồ thị trạng thái hữu hạn (StateGraph) với các node xử lý chuyên biệt. Luồng thực thi này cho phép kiểm soát chặt chẽ quá trình luân chuyển dữ liệu giữa các node và tự động kích hoạt nhánh dự phòng (fallback) an toàn khi gặp sự cố từ API.</p>
          </article>
          <article class="card">
            <span class="number">2</span>
            <h3>Streaming SSE Minh bạch Tiến độ</h3>
            <p>Các tác vụ đọc hiểu và so sánh đa tài liệu thường kéo dài từ 30 đến 90 giây. Thay vì bắt người dùng ngồi nhìn màn hình trống, hệ thống liên tục truyền phát trạng thái xử lý từng bước (Search, Extraction, Cross-check) thông qua Server-Sent Events (SSE), mang lại trải nghiệm tương tác liền mạch và minh bạch.</p>
          </article>
          <article class="card">
            <span class="number">3</span>
            <h3>Định tuyến Mô hình Thông minh</h3>
            <p>Hệ thống sử dụng các mô hình nhỏ, tốc độ cao (như Gemini 1.5 Flash hoặc Llama-3-8B) cho các tác vụ định tuyến, phân loại và trích xuất sơ bộ; chỉ điều phối các mô hình lớn (như Claude 3.5 Sonnet hoặc GPT-4o) cho bước tổng hợp đa tài liệu phức tạp, giúp giảm 80% chi phí vận hành.</p>
          </article>
        </div>

        <div class="strip" style="margin-top: 0.2in">
          <strong>Quy trình Node Thực thi</strong>
          <p>Router Node (Phân tích truy vấn) → Researcher Node (API ArXiv/Semantic Scholar) → Filter Node (Chấm điểm Abstract &ge; 60%) → Reader Node (Marker trích xuất PDF) → Synthesizer Node (Lập bảng so sánh) → Guardrail Node (Kiểm chứng nguồn).</p>
        </div>

        <div style="margin-top: 0.16in; display: flex; flex-direction: column; gap: 0.08in;">
          <div class="team-row" style="grid-template-columns: 1.8in 1.4in 1fr;">
            <strong>LangGraph StateGraph</strong>
            <span class="pill" style="min-height: 0.2in; font-size: 8px;">Deterministic Flow</span>
            <p>Kiểm soát chặt chẽ luồng rẽ nhánh và chuyển trạng thái dữ liệu, loại bỏ hoàn toàn rủi ro hallucination loop.</p>
          </div>
          <div class="team-row" style="grid-template-columns: 1.8in 1.4in 1fr;">
            <strong>Server-Sent Events (SSE)</strong>
            <span class="pill" style="min-height: 0.2in; font-size: 8px;">Real-Time Pipeline</span>
            <p>Truyền tải sự kiện dạng dòng tới client, cập nhật tiến trình từng node giúp người dùng không phải chờ đợi trong mơ hồ.</p>
          </div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>05</span></div>
      </section>

      <!-- ==================== SLIDE 6: 3-TIER GUARDRAILS ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">05. Độ tin cậy & Guardrails</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Hệ thống 3 Tầng Bảo vệ: Triệt tiêu Ảo giác Trích dẫn & Kiểm soát Độ tin cậy</h2>
        <p class="lead">Thiết lập hàng rào kiểm soát chất lượng đa tầng nhằm triệt tiêu hoàn toàn hiện tượng bịa nguồn trích dẫn và minh bạch hóa mức độ tin cậy của từng điểm dữ liệu.</p>

        <div class="grid-3" style="margin-top: 0.22in">
          <article class="card">
            <span class="number">T1</span>
            <h3>TẦNG 1: CHẶN TỪ CỬA VÀO</h3>
            <p>Đánh giá độ liên quan của bài báo dựa trên Abstract trước khi tải toàn bộ tệp PDF, ngăn chặn các bài báo lạc đề làm nhiễu kho dữ liệu. Thiết lập ngưỡng điểm phù hợp &ge; 60%, loại bỏ ngay từ đầu các tài liệu không đáp ứng tiêu chuẩn nghiên cứu đặt ra.</p>
          </article>
          <article class="card">
            <span class="number">T2</span>
            <h3>TẦNG 2: MINH BẠCH HÓA</h3>
            <p>Mỗi giá trị trích xuất trong bảng so sánh đều được gán nhãn độ tin cậy (confidence score) và trích dẫn số trang cụ thể. Đối với các điểm dữ liệu có độ tin cậy thấp, giao diện sẽ tự động làm mờ để nghiên cứu viên nhận diện và kiểm tra chéo nhanh chóng.</p>
          </article>
          <article class="card">
            <span class="number">T3</span>
            <h3>TẦNG 3: XÁC THỰC TRÍCH DẪN TUYỆT ĐỐI</h3>
            <p>Báo cáo tổng hợp cuối cùng chỉ được phê duyệt xuất bản khi 100% các nhận định và số liệu đối chiếu đều được liên kết chính xác với Chunk ID đã được lưu trữ trong cơ sở dữ liệu. Mọi khẳng định thiếu nguồn đối chiếu đều bị loại bỏ ngay lập tức.</p>
          </article>
        </div>

        <div class="strip" style="margin-top: 0.2in">
          <strong>Nguyên tắc Bất biến</strong>
          <p>Không cam kết mô hình ngôn ngữ không bao giờ mắc lỗi suy luận tổng quát, nhưng hệ thống đảm bảo 100% nguồn trích dẫn là có thật, truy vết chính xác đến từng trang và dòng trong văn bản PDF gốc.</p>
        </div>

        <div class="metrics" style="margin-top: 0.2in; grid-template-columns: repeat(3, 1fr);">
          <div class="metric"><strong>&ge; 60%</strong><span>Ngưỡng điểm phù hợp Abstract để nạp tài liệu</span></div>
          <div class="metric"><strong>Dynamic Fading</strong><span>Tự động làm mờ điểm dữ liệu độ tin cậy thấp</span></div>
          <div class="metric"><strong>100% Grounded</strong><span>Tỷ lệ nhận định bắt buộc liên kết Chunk ID nguồn</span></div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>06</span></div>
      </section>

      <!-- ==================== SLIDE 7: VISUAL COMPARISON MATRIX ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">06. Trực quan hóa Tri thức</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Ma trận So sánh Đối chiếu Đa chiều & Bản đồ Khoảng trống</h2>
        <p class="lead">Tự động cấu trúc hóa hàng trăm trang tài liệu học thuật rời rạc thành ma trận so sánh đối sánh chi tiết và biểu đồ phân tích khoảng trống nghiên cứu có thể hành động.</p>

        <div style="display: grid; grid-template-columns: 5.6in 1fr; gap: 0.22in; margin-top: 0.24in; align-items: stretch;">
          <div style="display: flex; flex-direction: column; gap: 0.16in;">
            <article class="card" style="flex: 1;">
              <h3>Ma trận So sánh Đa tiêu chí (Comparison Matrix)</h3>
              <p>Tự động trích xuất và đối chiếu các bài báo khoa học dựa trên các tiêu chí học thuật chuẩn mực: Phương pháp tiếp cận (Methodology), Tập dữ liệu (Datasets), Độ đo thực nghiệm (Metrics), Kết quả nổi bật (Key Findings) và Hạn chế cố hữu (Limitations).</p>
              <ul>
                <li>Hỗ trợ tương tác trực tiếp: nhấp vào bất kỳ ô thông tin nào để mở ngay đoạn trích dẫn nguồn trong file PDF gốc.</li>
                <li>Tích hợp xuất dữ liệu linh hoạt sang các định dạng học thuật tiêu chuẩn như LaTeX Table, CSV và Markdown.</li>
              </ul>
            </article>
            <article class="card featured" style="flex: 1;">
              <h3>Phát hiện Khoảng trống Nghiên cứu (Research Gaps)</h3>
              <p>Thuật toán phân tích tổng hợp giúp chỉ ra các khu vực kiến thức chưa được khai phá, những hạn chế chung giữa các nghiên cứu hiện hành và đề xuất hướng nghiên cứu tiềm năng tiếp theo cho tác giả.</p>
              <ul>
                <li>Bản đồ trích dẫn (Citation Network) phân cụm các trường phái nghiên cứu đối lập và bổ trợ.</li>
                <li>Phân tích tiến trình thời gian (Timeline Evolution) làm rõ sự phát triển của các phương pháp cốt lõi.</li>
              </ul>
            </article>
          </div>

          <div style="display: flex; flex-direction: column; justify-content: space-between;">
            <div style="border: 1px solid var(--hairline); border-radius: 10px; overflow: hidden; background: #fff; box-shadow: 0 8px 24px rgba(32,32,32,0.06); height: 3.1in;">
              <img src="{gaps_b64}" alt="Lumen Research Gaps Discovery Interface" style="width: 100%; height: 100%; object-fit: cover; object-position: top;" />
            </div>
            <div style="border: 1px solid var(--hairline); border-radius: 10px; background: var(--surface-bone); padding: 0.1in 0.16in; display: flex; align-items: center; justify-content: space-between;">
              <div>
                <strong style="color: var(--ink); font-size: 11px; display: block;">Phát hiện Mâu thuẫn & Khoảng trống Nghiên cứu (Gaps & Conflicts)</strong>
                <span style="color: var(--charcoal); font-size: 9.5px;">Tự động tổng hợp các thiếu sót thực nghiệm và mâu thuẫn giữa các công trình khoa học</span>
              </div>
              <span class="pill success" style="min-height: 0.22in; font-size: 8px;">Gaps Identified</span>
            </div>
          </div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>07</span></div>
      </section>

      <!-- ==================== SLIDE 8: EMPIRICAL EVALUATION ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">07. Đánh giá Thực nghiệm</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Kết quả Đo lường Thực nghiệm & Tối ưu Chi phí</h2>
        <p class="lead">Đo lường định lượng trên tập dữ liệu đối chuẩn gồm 50 bài báo khoa học thuộc lĩnh vực Học máy và Khoa học máy tính.</p>

        <div style="margin-top: 0.2in;">
          <table>
            <thead>
              <tr>
                <th style="width: 28%;">Chỉ số Đánh giá (Evaluation Metrics)</th>
                <th style="width: 24%;">ChatGPT-4o Thường</th>
                <th style="width: 24%;">RAG Cơ bản (Dense Search)</th>
                <th style="width: 24%; color: var(--ink); background: var(--surface-bone);">Lumen Multi-Agent (Đề xuất)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Tỷ lệ Ảo giác Nguồn Trích dẫn (Citation Hallucination)</td>
                <td>47.0% (Rất cao - bịa nguồn)</td>
                <td>18.5% (Còn trích dẫn nhầm)</td>
                <td><strong>0.0% (Kiểm chứng 100% Chunk ID)</strong></td>
              </tr>
              <tr>
                <td>Khẳng định có Bằng chứng Cấp dòng (Sentence Grounding)</td>
                <td>~30% (Chủ yếu suy diễn)</td>
                <td>~65% (Ngữ cảnh chung)</td>
                <td><strong>100% (Strict Attribution)</strong></td>
              </tr>
              <tr>
                <td>Độ bao phủ Thông tin (Recall@10)</td>
                <td>N/A (Chỉ theo bộ nhớ)</td>
                <td>68.2%</td>
                <td><strong>96.4% (+28.2% qua Hybrid Search)</strong></td>
              </tr>
              <tr>
                <td>Bảo toàn Cấu trúc Bảng & Công thức</td>
                <td>32.0% (Vỡ cấu trúc)</td>
                <td>45.0% (Mất ngữ cảnh bảng)</td>
                <td><strong>94.5% (Marker Deep-learning API)</strong></td>
              </tr>
              <tr>
                <td>Chi phí API Trung bình / Lần tổng quan</td>
                <td>~$1.80</td>
                <td>~$0.95</td>
                <td><strong>~$0.36 (-80% qua Model Routing)</strong></td>
              </tr>
              <tr>
                <td>Thời gian Hoàn tất Báo cáo Tổng quan</td>
                <td>3 - 5 phút (Chờ đợi)</td>
                <td>1 - 2 phút</td>
                <td><strong>45 giây (Song song hóa qua SSE)</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="metrics" style="margin-top: 0.2in; grid-template-columns: repeat(4, 1fr);">
          <div class="metric"><strong>0.0%</strong><span>Ảo giác nguồn trích dẫn</span></div>
          <div class="metric"><strong>100%</strong><span>Trích dẫn xác thực qua Chunk ID</span></div>
          <div class="metric"><strong>96.4%</strong><span>Độ bao phủ truy xuất Recall@10</span></div>
          <div class="metric"><strong>-80%</strong><span>Chi phí API nhờ Model Routing</span></div>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>08</span></div>
      </section>

      <!-- ==================== SLIDE 9: LESSONS & ROADMAP ==================== -->
      <section class="slide">
        <div class="top-row">
          <span class="pill">08. Đúc kết Kỹ thuật</span>
          <div class="logo">lumen</div>
        </div>
        <h2 style="margin-top: 0.16in">Kinh nghiệm Thiết kế Agent & Định hướng Phát triển</h2>
        <p class="lead">Những bài học xương máu trong quá trình phát triển Agent tự hành và lộ trình nâng cấp hạ tầng phục vụ môi trường học thuật chuyên nghiệp.</p>

        <div class="grid-3" style="margin-top: 0.22in">
          <article class="card">
            <span class="number">1</span>
            <h3>State Machine Vượt trội hơn ReAct Tự do</h3>
            <p>Việc kiểm soát chặt chẽ trạng thái bằng đồ thị hữu hạn (Finite StateGraph) mang lại tính ổn định và khả năng gỡ lỗi vượt trội so với các mô hình vòng lặp Agent tự do (Autonomous ReAct Loops) vốn rất dễ rơi vào tình trạng lặp vô hạn hoặc suy diễn lạc đề.</p>
          </article>
          <article class="card">
            <span class="number">2</span>
            <h3>Chất lượng Dữ liệu hơn Kích thước Model</h3>
            <p>Đầu tư công sức vào pipeline làm sạch dữ liệu PDF (sử dụng Marker và phân đoạn theo cây tiêu đề) mang lại bước nhảy vọt về độ chính xác lớn hơn nhiều so với việc chỉ đơn thuần thay đổi mô hình lớn hơn, đồng thời giúp tiết kiệm đến 80% chi phí vận hành.</p>
          </article>
          <article class="card">
            <span class="number">3</span>
            <h3>Minh bạch Hóa Trải nghiệm Thời gian thực</h3>
            <p>Khi xây dựng các ứng dụng Agent có thời gian thực thi dài, việc truyền phát trạng thái từng bước qua Server-Sent Events (SSE) và giao diện trực quan giúp biến quá trình chờ đợi thành trải nghiệm tương tác đáng tin cậy cho người dùng chuyên nghiệp.</p>
          </article>
        </div>

        <div class="grid-2" style="margin-top: 0.22in">
          <article class="card bone">
            <h3>Lộ trình Nâng cấp Tính năng Kỹ thuật</h3>
            <ul>
              <li>Tích hợp các cơ sở dữ liệu học thuật có bản quyền thông qua giao thức thư viện đại học (IEEE Xplore, ScienceDirect, ACM).</li>
              <li>Mô đun tự động trích xuất mã nguồn thực nghiệm (Code Reproducibility Extractor) từ các liên kết GitHub đính kèm trong bài báo.</li>
            </ul>
          </article>
          <article class="card featured">
            <h3>Khả năng Triển khai Doanh nghiệp & Nghiên cứu</h3>
            <ul>
              <li>Đóng gói kiến trúc theo chuẩn container microservices độc lập, tối ưu hóa khả năng mở rộng quy mô trên hạ tầng Kubernetes.</li>
              <li>Hỗ trợ triển khai On-premise với các mô hình mã nguồn mở cục bộ (vLLM / Ollama) phục vụ các viện nghiên cứu đòi hỏi bảo mật tuyệt đối.</li>
            </ul>
          </article>
        </div>

        <div class="footer"><span>Lumen · Autonomous Literature Review Agent</span><span>09</span></div>
      </section>

      <!-- ==================== SLIDE 10: CONCLUSION & DISCUSSION ==================== -->
      <section class="slide thanks">
        <div style="max-width: 6.8in;">
          <h1 style="margin-top: 0.42in; color: #ffffff; font-size: 38px;">TỔNG KẾT & TRAO ĐỔI KỸ THUẬT</h1>
          <p style="margin-top: 0.14in; font-size: 14px; color: rgba(255,255,255,0.88); line-height: 1.45;">
            Lumen - Nền tảng AI Tự hành Chuyên sâu cho Nghiên cứu Học thuật Đa tài liệu
          </p>
          <p style="margin-top: 0.14in; font-size: 11.2px; color: rgba(255,255,255,0.72); line-height: 1.58;">
            Hệ thống giải quyết trọn vẹn bài toán trích xuất dữ liệu học thuật phức tạp, kết hợp luồng Multi-Agent kiểm soát trạng thái chặt chẽ và hệ thống Guardrails 3 tầng triệt tiêu hoàn toàn hiện tượng tạo trích dẫn ảo giác. Sẵn sàng cho triển khai và mở rộng quy mô.
          </p>

          <div style="margin-top: 0.3in; display: flex; flex-direction: column; gap: 0.12in;">
            <div style="display: flex; align-items: center; gap: 0.14in; background: rgba(255,255,255,0.08); padding: 0.12in 0.18in; border-radius: 8px; border: 1px solid rgba(255,255,255,0.15);">
              <strong style="color: #fff; font-size: 12px; min-width: 1.7in;">Triệt tiêu ảo giác trích dẫn:</strong>
              <span style="color: rgba(255,255,255,0.85); font-size: 10.8px;">100% trích dẫn và số liệu được đối chiếu đến từng số trang và đoạn văn PDF gốc</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.14in; background: rgba(255,255,255,0.08); padding: 0.12in 0.18in; border-radius: 8px; border: 1px solid rgba(255,255,255,0.15);">
              <strong style="color: #fff; font-size: 12px; min-width: 1.7in;">Tối ưu hóa hiệu năng:</strong>
              <span style="color: rgba(255,255,255,0.85); font-size: 10.8px;">Tiết kiệm 80% chi phí API nhờ chiến lược Dynamic Model Routing</span>
            </div>
            <div style="display: flex; align-items: center; gap: 0.14in; background: rgba(255,255,255,0.08); padding: 0.12in 0.18in; border-radius: 8px; border: 1px solid rgba(255,255,255,0.15);">
              <strong style="color: #fff; font-size: 12px; min-width: 1.7in;">Trải nghiệm minh bạch:</strong>
              <span style="color: rgba(255,255,255,0.85); font-size: 10.8px;">Server-Sent Events streaming loại bỏ thời gian chờ màn hình trống</span>
            </div>
          </div>
        </div>

        <div class="thanks-card">
          <h2>Tài nguyên Kỹ thuật Dự án</h2>
          <p style="color: var(--charcoal); font-size: 10px; margin-top: 0.04in;">Mã nguồn mở và tài liệu kiểm thử hệ thống</p>

          <div style="margin-top: 0.2in; padding: 0.12in 0.15in; border-radius: 8px; background: var(--surface-bone); border: 1px solid var(--hairline);">
            <span style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; text-transform: uppercase; color: var(--charcoal); letter-spacing: 0.5px; line-height: 1.3;">Kho mã nguồn (GitHub Repository)</span>
            <a href="https://github.com/vietlinhh02/lumen-agent" target="_blank" style="text-decoration: none; color: inherit; display: block;">
              <strong style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--ink); margin-top: 5px;">github.com/vietlinhh02/lumen-agent</strong>
            </a>
            <span style="display: block; font-size: 9.6px; color: var(--charcoal); margin-top: 3px;">Toàn bộ source code Backend (FastAPI), Frontend (React) và LangGraph Workflows</span>
          </div>

          <div style="margin-top: 0.12in; padding: 0.12in 0.15in; border-radius: 8px; background: var(--surface-bone); border: 1px solid var(--hairline);">
            <span style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; text-transform: uppercase; color: var(--charcoal); letter-spacing: 0.5px; line-height: 1.3;">Video Minh họa Hệ thống (Demo Screencast)</span>
            <a href="https://youtu.be/uNt316BZaY8" target="_blank" style="text-decoration: none; color: inherit; display: block;">
              <strong style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--ink); margin-top: 5px;">youtu.be/uNt316BZaY8</strong>
            </a>
            <span style="display: block; font-size: 9.6px; color: var(--charcoal); margin-top: 3px;">Quá trình Agent tự hành tìm kiếm, trích xuất và lập ma trận đối chiếu thời gian thực</span>
          </div>

          <div style="margin-top: 0.12in; padding: 0.12in 0.15in; border-radius: 8px; background: var(--surface-bone); border: 1px solid var(--hairline);">
            <span style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700; text-transform: uppercase; color: var(--charcoal); letter-spacing: 0.5px; line-height: 1.3;">Tài liệu Kiến trúc & API Specs</span>
            <a href="https://github.com/vietlinhh02/lumen-agent/tree/main/docs" target="_blank" style="text-decoration: none; color: inherit; display: block;">
              <strong style="display: block; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--ink); margin-top: 5px;">github.com/vietlinhh02/lumen-agent/docs</strong>
            </a>
            <span style="display: block; font-size: 9.6px; color: var(--charcoal); margin-top: 3px;">Sơ đồ StateGraph, đặc tả schemas Pydantic và cấu hình Qdrant Vector Index</span>
          </div>

          <p class="quote">
            "Trong nghiên cứu học thuật, một kết quả tổng quan chỉ thực sự có giá trị khi mọi nguồn trích dẫn đều được kiểm chứng độc lập tới từng dòng trong văn bản gốc."
          </p>
        </div>

        <div class="logo" style="position: absolute; left: 0.72in; bottom: 0.3in; color: #ffffff;">lumen</div>
        <p style="position: absolute; right: 0.72in; bottom: 0.3in; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(255, 255, 255, 0.55);">
          Lumen Technical Presentation Deck · Slide 10 / 10
        </p>
      </section>

    </main>
  </body>
</html>
"""

output_path = '/home/eddiesngu/Desktop/Học tập và nghiên cứu/VinUni/old/C2-App-053/pitch_materials/lumen_pixta_presentation.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"Generated DESIGN.md embedded HTML at {output_path} ({len(html_content)} bytes)")
