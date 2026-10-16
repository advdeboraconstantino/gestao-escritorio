"""Classificação do ato publicado: o que deve ser feito e qual o prazo.

Regras baseadas nos textos padronizados do e-SAJ/DJEN. Quando o despacho não
traz o número de dias, aplica-se o prazo legal usual e isso fica registrado na
observação, para conferência humana. Nada aqui substitui a leitura da
publicação pela advogada responsável.
"""
import re
import unicodedata
from datetime import date

MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7,
         "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def _juizado(pub, t):
    o = norm(pub.get("orgao", "")) + " " + norm(pub.get("classe", ""))
    return ("JUIZADO" in o or "COLEGIO RECURSAL" in o or "RECURSO INOMINADO" in t
            or "JUIZADO ESPECIAL" in t)


def _dias_explicitos(t):
    m = re.search(r"(?:NO PRAZO DE|PRAZO:?|PRAZO COMUM DE|EM|POR|DENTRO DE)\s*(\d{1,3})\s*(?:\([A-Z\s]+\))?\s*DIAS(\s*UTEIS|\s*CORRIDOS)?", t)
    if m:
        return int(m.group(1)), not (m.group(2) and "CORRIDOS" in m.group(2))
    return None, True


def _data_sessao(t):
    m = re.search(r"INICIO EM (\d{1,2}) DE ([A-Z]+) DE (\d{4})", t)
    if m and m.group(2) in MESES:
        return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
    m = re.search(r"REALIZADA (?:DE|EM):?\s*(\d{2})/(\d{2})/(\d{4})", t)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def _r(tipo, acao, dias=None, uteis=True, obs="", ciencia=False, sessao=None):
    return dict(tipoprazo=tipo, acao=acao, dias=dias, uteis=uteis, obs=obs,
                ciencia=ciencia, dataSessao=sessao)


def classificar(pub: dict) -> dict:
    t = norm(pub.get("texto", ""))
    jz = _juizado(pub, t)
    n, uteis = _dias_explicitos(t)

    # 1. Pauta de julgamento virtual
    if "PAUTADO EM SESSAO" in t or "SESSAO DE JULGAMENTO VIRTUAL" in t:
        s = _data_sessao(t)
        return _r("Julgamento virtual",
                  "Julgamento virtual designado. Avaliar pedido de destaque, sustentação oral ou memoriais "
                  "até 48 horas antes do início da sessão (Res. CNJ 591/24 e NSCGJ, art. 714).",
                  obs="Sessão inicia em " + (s.strftime("%d/%m/%Y") if s else "data não identificada"),
                  sessao=s)

    # 2. Distribuição / entrada de recurso
    if "FICAM AS PARTES INTIMADAS ACERCA DA DISTRIBUICAO" in t or t.startswith("PROCESSO ENTRADO EM") \
            or "PROCESSOS DISTRIBUIDOS EM" in t:
        return _r("Ciência", "Ciência da distribuição/entrada do recurso no tribunal. Aguardar pauta.", ciencia=True)

    # 3. Processo suspenso
    if re.search(r"DETERMINO A SUSPENSAO|SUSPENDO O (PROCESSO|FEITO)|SOBRESTAMENTO DO FEITO", t):
        return _r("Ciência", "Processo suspenso. Sem prazo em curso; avaliar pedido de reconsideração ou prosseguimento.",
                  ciencia=True)

    # 4. Acórdão
    if "INTIMACAO DE ACORDAO" in t:
        return _r("Recurso", "Analisar acórdão: embargos de declaração (5 dias úteis) ou recurso cabível "
                  "(recurso extraordinário/especial: 15 dias úteis).", 5,
                  obs="Prazo fixado pelo menor prazo (embargos de declaração).")

    # 5. Recurso extraordinário: contrarrazões
    if "RECURSO EXTRAORDINARIO" in t and "CONTRARRAZ" in t:
        return _r("Contrarrazões", "Apresentar contrarrazões ao recurso extraordinário (CPC, art. 1.030).", 15)

    # 6. Contrarrazões (recurso da parte contrária)
    m_rec = re.search(r"RECURSO INTERPOSTO POR:?\s*([^)]+)\)", t)
    if m_rec and not any(e in m_rec.group(1) for e in ("PREFEITURA", "MUNICIPIO", "ESTADO", "FAZENDA", "SPPREV",
                                                        "PREVIDENCIA", "IPSM", "INSTITUTO")):
        return _r("Ciência", "Recurso interposto pela nossa cliente recebido; prazo de resposta é da parte contrária.",
                  ciencia=True)
    contra_nos = re.search(r"INTIME-SE A REQUERIDA PARA (OFERECIMENTO DAS )?CONTRARRAZ|"
                           r"DECORRIDO O PRAZO PARA APRESENTACAO DE CONTRARRAZ|JA APRESENTADAS AS CONTRARRAZ", t)
    if not contra_nos and re.search(r"CONTRARRAZ|RESPONDER, NO PRAZO LEGAL|RECORRIDO\s*\(A\)\s*A RESPONDER|"
                                    r"INTIME-SE O RECORRIDO", t):
        if "AGRAVO" in t and "CONTRAMINUTA" in t:
            return _r("Contrarrazões", "Apresentar contraminuta ao agravo.", n or 15)
        if jz:
            return _r("Contrarrazões", "Apresentar contrarrazões ao recurso inominado da parte contrária "
                      "(Lei 9.099/95, art. 42, §2º, c/c Lei 12.153/09, art. 27).", n or 10)
        return _r("Contrarrazões", "Apresentar contrarrazões à apelação da parte contrária (CPC, art. 1.010, §1º).",
                  n or 15)
    if contra_nos:
        return _r("Ciência", "Verificar se as contrarrazões já foram protocoladas; autos seguirão ao tribunal.",
                  ciencia=True)

    # 7. Sentença
    if re.search(r"JULGO (PARCIALMENTE )?(PROCEDENTE|IMPROCEDENTE)S?|JULGO PROCEDENTES|JULGO IMPROCEDENTES|"
                 r"JULGO PARCIALMENTE PROCEDENTES", t):
        if jz:
            return _r("Recurso", "Analisar sentença: recurso inominado (10 dias úteis, Lei 9.099/95, art. 42) "
                      "ou embargos de declaração (5 dias úteis). Se favorável, aguardar recurso da parte contrária.", 10)
        return _r("Recurso", "Analisar sentença: apelação (15 dias úteis) ou embargos de declaração (5 dias úteis). "
                  "Se favorável, aguardar recurso da parte contrária.", 15)

    # 7b. Despacho inicial de citação (prazo é da parte contrária), salvo se também houver ordem ao autor
    if re.search(r"CITE-SE", t) and not re.search(r"(EMENDAR|REGULARIZ|JUNTAR|COMPROVAR|SOB PENA DE INDEFERIMENTO)", t):
        return _r("Ciência", "Despacho inicial: citação da parte contrária. Aguardar a contestação.", ciencia=True)

    # 8. Réplica
    t_rep = t.replace("POR OCASIAO DA CONTESTACAO E DA REPLICA", "")
    if re.search(r"(EM|A|PARA) REPLICA|REPLICA,? (NO PRAZO|EM \d)|SOBRE A CONTESTACAO|MANIFESTE-SE .{0,60}REPLICA", t_rep):
        return _r("Manifestação", "Apresentar réplica à contestação (CPC, arts. 350 e 351).", n or 15,
                  obs="" if n else "Despacho fala em \"prazo legal\": aplicado 15 dias úteis.")

    # 9. Impugnação ao cumprimento de sentença
    if "SOBRE A IMPUGNACAO" in t:
        return _r("Manifestação", "Manifestar-se sobre a impugnação ao cumprimento de sentença.", n or 15)

    # 10. Laudo pericial
    if "LAUDO" in t and re.search(r"MANIFEST", t):
        return _r("Manifestação", "Manifestar-se sobre o laudo pericial.", n or 15)

    # 11. Intimação dirigida à parte contrária
    if re.search(r"VISTAS? DOS AUTOS AO (REU|EXECUTADO)|INTIME-SE A EXECUTADA PARA|INTIME-SE A PARTE RE |"
                 r"INTIME-SE A (O )?RE(U)? PARA|INTIME-SE A \(O\) RE \(U\)|NOS MOLDES DO ART\.\s*535", t) and not re.search(r"AUTOR|EXEQUENTE|VENCEDOR", t[:600]):
        return _r("Ciência", "Ato dirigido à parte contrária. Acompanhar.", ciencia=True)

    # 12. Homologação de cálculos
    if re.search(r"HOMOLOGO O CALCULO|HOMOLOGO OS CALCULOS", t):
        return _r("Petição", "Cálculos homologados. Após o decurso do prazo recursal, requerer a expedição de "
                  "RPV/precatório por incidente próprio.", n or 30)

    # 12b. Cumprimento de sentença contra a Fazenda: intimação do ente (art. 535) e opção de renúncia ao teto do RPV
    if re.search(r"ART\.?\s*535", t) and "RENUNCIA" in t:
        return _r("Manifestação", "Fazenda intimada para impugnar (art. 535 do CPC). Avaliar com o cliente a renúncia "
                  "ao valor excedente ao teto de RPV, no mesmo prazo, se for vantajoso.", 30,
                  obs="Prazo de 30 dias úteis contado em paralelo ao da Fazenda.")

    # 13. Manifestação com prazo expresso
    if n:
        acao = "Manifestar-se nos autos conforme determinado."
        if "VENCEDOR" in t:
            acao = "Manifestar-se (vencedor) e, se for o caso, instaurar o cumprimento de sentença."
        elif "PAGAMENTO" in t:
            acao = "Intimação para pagamento ou manifestação sobre pagamento. Conferir quem é o devedor."
        elif "EMENDA" in t or "REGULARIZ" in t:
            acao = "Emendar a inicial ou regularizar o que foi determinado."
        elif "DOCUMENTO" in t:
            acao = "Apresentar documentos ou manifestar-se sobre os documentos juntados."
        return _r("Manifestação", acao, n, uteis)

    # 14. Manifestação sem prazo
    if re.search(r"MANIFESTE-SE|MANIFESTAR-SE|DIGA(M)? (O|A|AS) PARTE|ESPECIFIQUEM|ESPECIFIQUE", t):
        return _r("Manifestação", "Manifestar-se nos autos conforme determinado.", 5,
                  obs="Despacho sem prazo expresso: aplicado 5 dias úteis (CPC, art. 218, §3º).")

    return _r("Ciência", "Ciência da publicação. Nenhum prazo identificado automaticamente.", ciencia=True)
