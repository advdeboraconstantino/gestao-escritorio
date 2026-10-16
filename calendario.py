"""Calendário forense (TJSP) e contagem de prazos em dias úteis.

Regra adotada (Lei 11.419/2006, art. 4º, §§3º e 4º; CPC, arts. 219, 220 e 224):
  * publicação = 1º dia útil seguinte à disponibilização no DJEN;
  * o prazo começa no 1º dia útil seguinte à publicação;
  * contam-se apenas dias úteis (inclusive nos Juizados: Lei 9.099/95, art. 12-A);
  * de 20/12 a 20/01 os prazos ficam suspensos (CPC, art. 220).

Critério conservador: na dúvida, o dia é considerado útil (o prazo vence mais cedo).
Feriados municipais ou suspensões de expediente do TJSP podem ser acrescentados
pelo sistema (Firestore: config/feriados, campo "datas" = lista "AAAA-MM-DD").
"""
from datetime import date, timedelta


def _pascoa(ano: int) -> date:
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_ano(ano: int) -> set:
    p = _pascoa(ano)
    fixos = [(1, 1), (4, 21), (5, 1), (7, 9), (9, 7), (10, 12), (11, 2),
             (11, 15), (11, 20), (12, 8), (12, 25)]
    s = {date(ano, m, d) for m, d in fixos}
    s |= {p - timedelta(days=48), p - timedelta(days=47),  # Carnaval
          p - timedelta(days=2),                             # Sexta-feira Santa
          p + timedelta(days=60)}                            # Corpus Christi
    return s


class Calendario:
    def __init__(self, extras=None):
        self.extras = set()
        for x in extras or []:
            try:
                self.extras.add(date.fromisoformat(str(x)[:10]))
            except ValueError:
                pass
        self._cache = {}

    def _fer(self, ano):
        if ano not in self._cache:
            self._cache[ano] = feriados_ano(ano)
        return self._cache[ano]

    def suspenso(self, d: date) -> bool:
        return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)

    def util(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self._fer(d.year) and d not in self.extras

    def prox_util(self, d: date) -> date:
        d += timedelta(days=1)
        while not self.util(d):
            d += timedelta(days=1)
        return d

    def publicacao(self, disponibilizacao: date) -> date:
        return self.prox_util(disponibilizacao)

    def vencimento(self, publicacao: date, dias: int, uteis: bool = True) -> date:
        """Último dia do prazo contado a partir da publicação."""
        d = publicacao
        if uteis:
            n = 0
            while n < dias:
                d = self.prox_util(d)
                if self.suspenso(d):
                    continue
                n += 1
            return d
        d = publicacao + timedelta(days=dias)
        while not self.util(d):
            d += timedelta(days=1)
        return d

    def menos_uteis(self, d: date, n: int) -> date:
        while n > 0:
            d -= timedelta(days=1)
            if self.util(d):
                n -= 1
        return d

    def uteis_entre(self, a: date, b: date) -> int:
        """Dias úteis de a (exclusive) até b (inclusive). Negativo se b < a."""
        if b < a:
            return -self.uteis_entre(b, a)
        n, d = 0, a
        while d < b:
            d += timedelta(days=1)
            if self.util(d):
                n += 1
        return n
