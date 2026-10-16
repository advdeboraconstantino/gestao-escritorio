"""Extração de publicações dos e-mails do Recorte Digital OAB/SP e da AASP."""
import re
import html as _html
import unicodedata
from datetime import date

RX_CNJ = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")
RX_DATA = r"(\d{2}/\d{2}/\d{4})"

ENTES = ("PREFEITURA", "MUNICIPIO", "MUNICÍPIO", "ESTADO DE SAO PAULO", "ESTADO DE SÃO PAULO",
         "FAZENDA", "SPPREV", "SAO PAULO PREVIDENCIA", "SÃO PAULO PREVIDÊNCIA", "IPSM", "IPMJ",
         "INSTITUTO DE PREVIDENCIA", "INSTITUTO DE PREVIDÊNCIA", "IPREM", "JUIZO EX OFFICIO",
         "JUÍZO EX OFFICIO", "UNIAO", "UNIÃO", "INSS", "CAMARA MUNICIPAL", "CÂMARA MUNICIPAL")


def html_para_texto(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", h)
    h = re.sub(r"(?i)</td>|</th>", " | ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return _html.unescape(h)


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _data(s):
    try:
        d, m, a = s.split("/")
        return date(int(a), int(m), int(d))
    except Exception:
        return None


def _cabecalho(texto: str, numero: str):
    """Classe, assunto e nome do cliente a partir do cabeçalho padrão do e-SAJ."""
    classe = assunto = cliente = ""
    t = texto
    m = re.search(r"Recorrente:\s*([^-;]+?)\s*[-;]\s*Recorrid[oa]:\s*([^-;]+?)(?:\s*[-;]|$)", t)
    if not m:
        m = re.search(r"Apelante:\s*([^-;]+?)\s*[-;]\s*Apelad[oa]:\s*([^-;]+?)(?:\s*[-;]|$)", t)
    if not m:
        m = re.search(r"Agravante:\s*([^-;]+?)\s*[-;]\s*Agravad[oa]:\s*([^-;]+?)(?:\s*[-;]|$)", t)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
        cliente = b if any(e in _sem_acento(a).upper() for e in map(_sem_acento, ENTES)) else a
    ma = re.search(r"Assunto:\s*([^;]+);", t) or re.search(r";\s*%s;\s*([^;]+);" % re.escape(numero), t)
    if ma:
        assunto = ma.group(1).strip()
    i = t.find(numero)
    if i >= 0:
        resto = t[i + len(numero):]
        resto = re.sub(r"^\s*(/\d+)?\s*(\(processo principal [^)]*\))?\s*", "", resto)
        corte = re.split(r"\s-\s(?:Vistos|VISTOS|Fls\.|Diante|Ante|Trata-se|Manifeste|Recebo|Certid|Considerando|Intime|Vistas|Processo Desarquivado|A materia|A matéria|O pedido|Revogo|Cumpra|Aguarde|Defiro|Concedo|Ciente|Verifica|Em \d|Fl)", resto, maxsplit=1)[0]
        corte = re.sub(r"^[\s-]+", "", corte)
        partes = [p.strip() for p in corte.split(" - ") if p.strip()]
        if partes and partes[0].lower().startswith("processo digital"):
            partes = partes[1:]
        if partes:
            classe = partes[0]
        recursal = bool(re.search(r"Recorrente:|Apelante:|Agravante:", t))
        if len(partes) > 1 and not assunto and not recursal:
            assunto = partes[1]
        if not cliente:
            for p in partes[2:]:
                if p and not any(_sem_acento(e) in _sem_acento(p).upper() for e in ENTES) and len(p) < 90:
                    cliente = p
                    break
    return classe[:120], assunto[:120], cliente[:120]


def parse_oab(texto: str, msg_id: str = ""):
    t = _flat(texto)
    blocos = re.split(r"\|?\s*Publica[çc][ãa]o:\s*\d+\.\s*\|?", t)
    out = []
    for b in blocos[1:]:
        md = re.search(r"Disponibiliza[çc][ãa]o:\s*" + RX_DATA, b)
        mp = re.search(r"Data de Publica[çc][ãa]o:\s*" + RX_DATA, b)
        mn = re.search(r"PROCESSO:\s*" + RX_CNJ.pattern, b) or RX_CNJ.search(b)
        if not (md and mn):
            continue
        num = mn.group(1)
        mv = re.search(r"Vara:\s*(.+?)\s*\|", b)
        corpo = b.split("||", 1)[1] if "||" in b else b
        corpo = re.split(r"\|\|\|\s*POLO", corpo)[0]
        corpo = re.sub(r"\s*\|\s*Total de Publica[çc][õo]es.*$", "", corpo).strip(" |")
        corpo = re.sub(r"\s*\|\s*$", "", corpo)
        classe, assunto, cliente = _cabecalho(corpo, num)
        out.append(dict(fonte="OAB/SP Recorte Digital", emailId=msg_id, numero=num,
                        disponibilizacao=_data(md.group(1)), publicacao=_data(mp.group(1)) if mp else None,
                        orgao=(mv.group(1).strip() if mv else "")[:160], texto=corpo[:6000], truncado=False,
                        classe=classe, assunto=assunto, cliente=cliente))
    return out


def parse_aasp(texto: str, msg_id: str = ""):
    t = _flat(texto)
    blocos = re.split(r"DJEN[A-Z0-9\-]*\s*Processo n[ºo°]?:\s*", t)
    out = []
    for b in blocos[1:]:
        mn = RX_CNJ.match(b) or RX_CNJ.search(b[:60])
        md = re.search(r"Disponibiliza[çc][ãa]o:\s*" + RX_DATA, b)
        if not (mn and md):
            continue
        num = mn.group(1)
        mo = re.search(r"[ÓO]rg[ãa]o:\s*(.+?)\s*Data de disponibiliza", b)
        corpo = b
        mc = re.search(r"Advogado\(s\)\s*(.*)", b)
        if mc:
            corpo = mc.group(1)
            corpo = re.sub(r"^(?:[A-ZÀ-Ú][A-ZÀ-Ú\s\.'´`-]+ OAB [A-Z]{2}-\d+\s*)+", "", corpo)
        trunc = "CONTINUA" in corpo
        corpo = re.split(r"<b>|\[\.\.\.\]|http://intimacoes", corpo)[0].strip()
        classe, assunto, cliente = _cabecalho(corpo, num)
        out.append(dict(fonte="AASP", emailId=msg_id, numero=num, disponibilizacao=_data(md.group(1)),
                        publicacao=None, orgao=(mo.group(1).strip() if mo else "")[:160], texto=corpo[:6000],
                        truncado=trunc, classe=classe, assunto=assunto, cliente=cliente))
    return out


def parse_email(remetente: str, texto: str, msg_id: str = ""):
    if "<html" in texto[:2000].lower() or "<table" in texto[:5000].lower():
        texto = html_para_texto(texto)
    if "recortedigital" in remetente:
        return parse_oab(texto, msg_id)
    if "aasp" in remetente:
        return parse_aasp(texto, msg_id)
    return []
