name: Daily Stock AI Report (BJT 12:00 & 16:00 + Telegram DM)

on:
  workflow_dispatch:      # 允许手动触发
  schedule:
    - cron: "0 4 * * *"   # UTC 04:00 = BJT 12:00 (午休)
    - cron: "0 8 * * *"   # UTC 08:00 = BJT 16:00 (收盘)

permissions:
  contents: write

concurrency:
  group: stock-ai-report-main
  cancel-in-progress: true

jobs:
  run:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo (full history)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # 建议确保 akshare 是最新版，因为数据接口经常变动
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pandas akshare mplfinance openai
          # 如果你有 requirements.txt，保留下面这行；如果没有，上面的 pip install 已经够用了
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Run script
        env:
          # API Key
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          # 核心修改：注入保密的 Prompt Template
          WYCKOFF_PROMPT_TEMPLATE: ${{ secrets.WYCKOFF_PROMPT_TEMPLATE }}
          # 其他配置
          SYMBOL: "600970"
          BARS_COUNT: "600" # 控制 K 线数量
          # 如果想用 DeepSeek，可以在这里加:
          # OPENAI_BASE_URL: "https://api.deepseek.com"
          # AI_MODEL: "deepseek-chat"
        run: |
          # 确保 data 和 reports 目录存在
          mkdir -p data reports
          python main.py

      - name: Commit and push reports (rebase-safe)
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          # 只添加 reports 文件夹 (忽略 data 文件夹里的 csv，避免仓库太大)
          git add reports/
          
          # 检查是否有变更
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            git commit -m "chore: daily report $(date +'%Y-%m-%d %H:%M')"
            git pull --rebase origin main
            git push origin HEAD:main
          fi

      - name: Notify Telegram (DM)
        if: success() 
        env:
          TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}
        run: |
          set -e
          
          # 查找最新的 md 文件
          REPORT_FILE=$(ls -1t reports/*.md 2>/dev/null | head -n 1 || true)
          
          if [ -z "$REPORT_FILE" ]; then
            echo "::warning::没有找到报告文件，跳过 Telegram 通知。"
            exit 0
          fi

          echo "Found report: $REPORT_FILE"

          TITLE=$(head -n 1 "$REPORT_FILE" | sed 's/^#\+\s*//g' | xargs || true)
          if [ -z "$TITLE" ]; then TITLE="Daily Stock AI Report"; fi

          # 摘要截取 (适配 Markdown 内容)
          SUMMARY=$(head -n 60 "$REPORT_FILE" | head -c 3500)

          # 构建消息
          MESSAGE="$TITLE

          文件：$REPORT_FILE

          摘要：
          $SUMMARY
          
          ... (点击链接查看完整版)
          Repo：${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}"

          # 发送消息
          curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TG_CHAT_ID}" \
            -d parse_mode="HTML" \
            --data-urlencode text="$MESSAGE"
