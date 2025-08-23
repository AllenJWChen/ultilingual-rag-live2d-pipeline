from typing import List, Dict

ANSWER_PROMPT = '''你是一位嚴謹的企業資料助理。根據提供的「來源片段」回答問題：
- 僅能使用來源片段的資訊，若不足請說明「目前資料不足以回答」
- 以條列清楚回覆，最後附上引用編號 [1][2]...

使用者問題：{q}

來源片段：
{contexts}

請用提問者的語言回答。
'''

def build_prompt(q: str, hits: List[Dict]) -> str:
    ctx = []
    for h in hits:
        snippet = h.get("text","")[:400].replace("\n", " ")
        ctx.append(f"[{h['rank']}] {snippet} (p={h.get('page')}, src={h.get('source')})")
    return ANSWER_PROMPT.format(q=q, contexts="\n".join(ctx))

def mock_llm_generate(prompt: str) -> str:
    # 演示用途：擷取前 3 段形成條列。實戰請接真 LLM。
    lines = [l for l in prompt.splitlines() if l.strip().startswith('[')]
    bullets = "\n".join(f"- {l}" for l in lines[:3])
    return bullets + "\n\n（示範回覆，請接真模型）"
