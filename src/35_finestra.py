# ==========================================================================================
# 5c. VITA DELLA FINESTRA: come il programma capisce che hai chiuso la finestra dell'app
# ==========================================================================================
# IDEA (spiegata semplice)
# ------------------------
# NeoTracker è composto da due parti che parlano tra loro:
#   - il "motore" (questo programma Python), che salva i dati e analizza le foto;
#   - la "finestra" (Edge o Chrome aperto in modalità app, cioè senza barra degli indirizzi
#     e senza schede), che mostra la pagina.
# Quando tu chiudi la finestra, il motore deve spegnersi da solo. Ma il motore non può
# "sentire" la chiusura direttamente: allora la pagina gli manda un piccolo segnale ("battito")
# ogni pochi secondi, come un cuore che batte. Se i battiti smettono, la finestra è chiusa.
#
#   - ogni pagina aperta ha un proprio numero (id) casuale e manda un "battito" ogni ~5 secondi;
#   - quando la pagina viene chiusa prova anche a mandare un "addio" (chiusura immediata);
#   - se per 6 secondi non c'è più NESSUNA pagina aperta, il motore si spegne (i 6 secondi
#     servono perché premendo F5 / "ricarica" la pagina sparisce e ricompare in un attimo:
#     non vogliamo spegnere tutto per un ricaricamento);
#   - se la finestra si blocca o il PC va in sospensione senza "addio", dopo 3 minuti di
#     silenzio la pagina è considerata chiusa;
#   - se il motore sta ANCORA analizzando una foto, aspetta la fine dell'analisi e poi si spegne
#     (così non perdi il lavoro); se nel frattempo riapri l'icona, la finestra torna.

GRAZIA_CHIUSURA_S = 6          # secondi senza pagine aperte prima di spegnere (copre il ricaricamento)
SILENZIO_MASSIMO_S = 180       # una pagina muta per 3 minuti è considerata chiusa (finestra bloccata)
FINESTRA_APERTA_S = 90         # entro quanti secondi dall'ultimo battito diciamo "la finestra è aperta"
ATTESA_PRIMA_FINESTRA_S = 600  # se nessuna finestra si apre entro 10 minuti dall'avvio, ci spegniamo


class StatoFinestra:
    """Tiene il conto delle pagine aperte e dice quando il programma deve spegnersi.

    Il tempo viene sempre passato dal chiamante (parametro `adesso`, in secondi): così nei test
    possiamo simulare minuti e ore in un istante, senza aspettare davvero.
    """

    def __init__(self, adesso=None):
        self._blocco = threading.Lock()                       # evita che due richieste modifichino insieme
        self.avviato = time.monotonic() if adesso is None else adesso
        self.pagine = {}                                      # id pagina -> istante dell'ultimo battito
        self.vista_almeno_una = False                         # è mai comparsa una finestra?
        self.vuoto_da = None                                  # da quando non ci sono più pagine (None = ce n'è almeno una)
        self.chiuse = {}                                      # pagine che hanno detto "addio": non possono più "riaprirsi"

    def azzera(self, adesso=None):
        """Riparte da capo (chiamata all'avvio del server): nessuna pagina, nessuna finestra mai vista."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.avviato, self.pagine, self.vista_almeno_una, self.vuoto_da = adesso, {}, False, None
            self.chiuse = {}

    # ---- segnali che arrivano dalla pagina ----
    def battito(self, id_pagina, adesso=None):
        """Una pagina dice "sono ancora qui"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            if id_pagina in self.chiuse:
                return          # un battito in ritardo (arrivato dopo l'addio) non deve far "risuscitare" una pagina chiusa
            self.pagine[id_pagina] = adesso
            self.vista_almeno_una = True
            self.vuoto_da = None                              # c'è almeno una pagina: annulla l'eventuale spegnimento

    def addio(self, id_pagina, adesso=None, definitivo=False):
        """Una pagina non c'è più.
        definitivo=True: è la pagina stessa a dirci "mi sto chiudendo" -> da ora i suoi eventuali battiti
        in ritardo vengono ignorati. definitivo=False: lo deduciamo noi dalla connessione caduta (potrebbe
        essere solo un'interruzione momentanea: se la pagina ricompare con lo stesso numero, vale)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self.pagine.pop(id_pagina, None)
            if definitivo:
                self.chiuse[id_pagina] = adesso
                while len(self.chiuse) > 500:                 # non teniamo l'elenco all'infinito
                    del self.chiuse[next(iter(self.chiuse))]
            if not self.pagine and self.vuoto_da is None:
                self.vuoto_da = adesso                        # parte il conto alla rovescia dei 6 secondi

    # ---- domande che fa il programma ----
    def _togli_pagine_mute(self, adesso):
        """Dimentica le pagine che non battono da troppo tempo (finestra bloccata o chiusa a forza)."""
        mute = [i for i, t in self.pagine.items() if adesso - t > SILENZIO_MASSIMO_S]
        for i in mute:
            del self.pagine[i]
        if mute and not self.pagine and self.vuoto_da is None:
            self.vuoto_da = adesso

    def finestra_aperta(self, adesso=None):
        """True se c'è una pagina che ha battuto di recente (serve alla seconda apertura dell'icona)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            return any(adesso - t <= FINESTRA_APERTA_S for t in self.pagine.values())

    def dopo_sospensione(self, adesso=None):
        """Il PC si è appena risvegliato: durante la sospensione nessuna pagina poteva battere,
        quindi facciamo finta che tutte abbiano battito adesso (altrimenti sembrerebbero chiuse)."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            for i in self.pagine:
                self.pagine[i] = adesso
            if self.vuoto_da is not None:
                self.vuoto_da = adesso
            self.avviato = max(self.avviato, adesso - 1)

    def da_spegnere(self, adesso=None, analisi_in_corso=False):
        """True quando il programma deve chiudersi. Chiamata ogni secondo dal "sorvegliante"."""
        adesso = time.monotonic() if adesso is None else adesso
        with self._blocco:
            self._togli_pagine_mute(adesso)
            if self.pagine:
                return False                                  # c'è ancora almeno una finestra aperta
            if analisi_in_corso:
                return False                                  # non interrompere un'analisi: finirà e poi ci spegniamo
            if self.vista_almeno_una:
                return self.vuoto_da is not None and adesso - self.vuoto_da >= GRAZIA_CHIUSURA_S
            return adesso - self.avviato >= ATTESA_PRIMA_FINESTRA_S   # nessuna finestra è mai comparsa


STATO_FINESTRA = StatoFinestra()
