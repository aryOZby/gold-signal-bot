#property copyright "gold-signal-bot"
#property version   "1.10"
#property description "Bridge: Python gold-signal-bot ↔ MT5 via Common/Files"

#include <Trade/Trade.mqh>

// השמות אחרי // מופיעים בחלון Inputs ב-MT5.
input double InpLot         = 0.01;                    // Lot (per position)
input bool   InpDryRun      = false;                   // Dry run (no orders)
input string InpMagicList   = "260908,260909,260910";  // Magics
input int    InpTimerMs     = 50;                      // Timer ms
input int    InpDeviation   = 30;                      // Deviation

CTrade trade;
string lastPosKeys = "";
long   magics[];

void ParseMagics()
{
   string parts[];
   int n = StringSplit(InpMagicList, ',', parts);
   ArrayResize(magics, 0);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      if(StringLen(parts[i]) == 0)
         continue;
      long m = StringToInteger(parts[i]);
      if(m <= 0)
         continue;
      int size = ArraySize(magics);
      ArrayResize(magics, size + 1);
      magics[size] = m;
   }
   if(ArraySize(magics) == 0)
   {
      ArrayResize(magics, 1);
      magics[0] = 260908;
   }
}

bool IsOurMagic(const long magic)
{
   for(int i = 0; i < ArraySize(magics); i++)
      if(magics[i] == magic)
         return true;
   return false;
}

// מיישר לוט ידני למדרגות שהברוקר מאפשר, כדי ש-0.007 לא ייפסל.
double NormalizeVolume(const string symbol, double volume)
{
   double vmin  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(vstep > 0.0)
      volume = MathRound(volume / vstep) * vstep;
   if(vmin > 0.0 && volume < vmin)
      volume = vmin;
   if(vmax > 0.0 && volume > vmax)
      volume = vmax;
   return NormalizeDouble(volume, 2);
}

void ShowStatus()
{
   string lot = (InpLot > 0.0)
                ? DoubleToString(InpLot, 2)
                : "from bot";
   Comment(
      "GoldSignalBridge\n",
      "symbol : ", _Symbol, "\n",
      "magics : ", InpMagicList, "\n",
      "lot    : ", lot, "\n",
      "mode   : ", (InpDryRun ? "DRY RUN - no orders sent" : "LIVE"), "\n",
      "open   : ", IntegerToString(PositionsTotal())
   );
}

int OnInit()
{
   ParseMagics();
   trade.SetExpertMagicNumber((int)magics[0]);
   trade.SetDeviationInPoints(InpDeviation);
   if(!EventSetMillisecondTimer(InpTimerMs))
      EventSetTimer(1);
   PrintFormat("GoldSignalBridge started: symbol=%s magics=%s lot=%s mode=%s",
               _Symbol, InpMagicList,
               (InpLot > 0.0 ? DoubleToString(InpLot, 2) : "from bot"),
               (InpDryRun ? "DRY RUN" : "LIVE"));
   if(InpDryRun)
      Print("WARNING: InpDryRun=true - commands are logged but no orders are sent.");
   WriteLot();
   ShowStatus();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

void OnTimer()
{
   WriteHeartbeat();
   WriteTick();
   WriteLot();
   ProcessCommands();
   DetectClosesAndWritePositions();
   ShowStatus();
}

void WriteHeartbeat()
{
   int h = FileOpen("gs_heartbeat.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, IntegerToString((int)TimeGMT()) + "\n");
   FileClose(h);
}

void WriteLot()
{
   int h = FileOpen("gs_lot.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, DoubleToString(InpLot, 4) + "\n");
   FileClose(h);
}

void WriteTick()
{
   int h = FileOpen("gs_tick.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   string line = "TICK|" + _Symbol + "|" +
                 DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_BID), _Digits) + "|" +
                 DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_ASK), _Digits) + "\n";
   FileWriteString(h, line);
   FileClose(h);
}

void ProcessCommands()
{
   string fname;
   long search = FileFindFirst("gs_cmd_*.txt", fname, FILE_COMMON);
   if(search == INVALID_HANDLE)
      return;
   do
   {
      ProcessOne(fname);
      FileDelete(fname, FILE_COMMON);
   }
   while(FileFindNext(search, fname));
   FileFindClose(search);
}

void ProcessOne(const string fname)
{
   int h = FileOpen(fname, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   string line = FileReadString(h);
   FileClose(h);
   StringTrimLeft(line);
   StringTrimRight(line);
   if(StringLen(line) == 0)
      return;

   string parts[];
   int n = StringSplit(line, '|', parts);
   if(n < 2)
      return;
   string action = parts[0];
   string uid = parts[1];

   if(action == "MARKET" && n >= 10)
      DoMarket(uid, parts);
   else if(action == "MODIFY" && n >= 5)
      DoModify(uid, parts);
   else
      WriteRes(uid, "ERR|bad_cmd");
}

void DoMarket(const string uid, string &parts[])
{
   string symbol   = parts[2];
   string side     = parts[3];
   double volume   = StringToDouble(parts[4]);
   double sl       = StringToDouble(parts[5]);
   double tp       = StringToDouble(parts[6]);
   int deviation   = (int)StringToInteger(parts[7]);
   long magic      = StringToInteger(parts[8]);
   string comment  = parts[9];

   if(!SymbolSelect(symbol, true))
   {
      WriteRes(uid, "ERR|symbol");
      return;
   }

   if(InpLot > 0.0)
      volume = InpLot;
   volume = NormalizeVolume(symbol, volume);

   if(InpDryRun)
   {
      PrintFormat("DRY RUN: skipped %s %s %.2f lots sl=%.2f tp=%.2f",
                  side, symbol, volume, sl, tp);
      WriteRes(uid, "ERR|DRY_RUN");
      return;
   }

   trade.SetExpertMagicNumber((int)magic);
   trade.SetDeviationInPoints(deviation);
   trade.SetTypeFillingBySymbol(symbol);

   bool ok = false;
   if(side == "BUY")
      ok = trade.Buy(volume, symbol, 0.0, sl, tp, comment);
   else
      ok = trade.Sell(volume, symbol, 0.0, sl, tp, comment);

   if(ok)
   {
      ulong ticket = trade.ResultOrder();
      if(ticket == 0)
         ticket = trade.ResultDeal();
      // הנפח נשלח בחזרה כדי שהדוחות ישקפו דריסת לוט מהגרף.
      string body = "OK|" + IntegerToString((long)ticket) + "|" +
                    DoubleToString(trade.ResultPrice(), 5) + "|" +
                    IntegerToString((int)trade.ResultRetcode()) + "|" +
                    DoubleToString(volume, 4);
      WriteRes(uid, body);
   }
   else
   {
      WriteRes(uid, "ERR|" + IntegerToString((int)trade.ResultRetcode()) + "|" + trade.ResultComment());
   }
}

void DoModify(const string uid, string &parts[])
{
   ulong ticket = (ulong)StringToInteger(parts[2]);
   if(!PositionSelectByTicket(ticket))
   {
      WriteRes(uid, "ERR|no_position");
      return;
   }
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   if(StringLen(parts[3]) > 0)
      sl = StringToDouble(parts[3]);
   if(StringLen(parts[4]) > 0)
      tp = StringToDouble(parts[4]);

   if(trade.PositionModify(ticket, sl, tp))
      WriteRes(uid, "OK|" + IntegerToString((long)ticket) + "|0|0");
   else
      WriteRes(uid, "ERR|" + IntegerToString((int)trade.ResultRetcode()));
}

void WriteRes(const string uid, const string body)
{
   string name = "gs_res_" + uid + ".txt";
   int h = FileOpen(name, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, "RES|" + uid + "|" + body + "\n");
   FileClose(h);
}

void DetectClosesAndWritePositions()
{
   string currentKeys = "";
   int h = FileOpen("gs_positions.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;

   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!IsOurMagic(PositionGetInteger(POSITION_MAGIC)))
         continue;
      string side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      string line = "POS|" +
         IntegerToString((long)ticket) + "|" +
         PositionGetString(POSITION_SYMBOL) + "|" +
         side + "|" +
         DoubleToString(PositionGetDouble(POSITION_VOLUME), 4) + "|" +
         DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN), 5) + "|" +
         DoubleToString(PositionGetDouble(POSITION_SL), 5) + "|" +
         DoubleToString(PositionGetDouble(POSITION_TP), 5) + "|" +
         DoubleToString(PositionGetDouble(POSITION_PROFIT), 2) + "|" +
         PositionGetString(POSITION_COMMENT) + "|" +
         IntegerToString((int)PositionGetInteger(POSITION_MAGIC));
      FileWriteString(h, line + "\n");
      currentKeys += IntegerToString((long)ticket) + ";";
   }
   FileClose(h);

   if(StringLen(lastPosKeys) > 0)
   {
      string olds[];
      int n = StringSplit(lastPosKeys, ';', olds);
      for(int i = 0; i < n; i++)
      {
         if(StringLen(olds[i]) == 0)
            continue;
         if(StringFind(currentKeys, olds[i] + ";") < 0)
            WriteClose((ulong)StringToInteger(olds[i]));
      }
   }
   lastPosKeys = currentKeys;
}

void WriteClose(const ulong ticket)
{
   double price = 0.0;
   double profit = 0.0;
   datetime t = TimeGMT();
   string reason = "UNKNOWN";

   if(HistorySelectByPosition(ticket))
   {
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;
         if(HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_OUT)
            continue;
         price = HistoryDealGetDouble(deal, DEAL_PRICE);
         profit = HistoryDealGetDouble(deal, DEAL_PROFIT)
                + HistoryDealGetDouble(deal, DEAL_SWAP)
                + HistoryDealGetDouble(deal, DEAL_COMMISSION);
         t = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
         long r = HistoryDealGetInteger(deal, DEAL_REASON);
         if(r == DEAL_REASON_TP)
            reason = "TP";
         else if(r == DEAL_REASON_SL)
            reason = "SL";
         else
            reason = "MANUAL";
      }
   }
   AppendClose(ticket, price, t, profit, reason);
}

void AppendClose(const ulong ticket, const double price, const datetime t, const double profit, const string reason)
{
   int h = FileOpen("gs_closed.txt", FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      h = FileOpen("gs_closed.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileSeek(h, 0, SEEK_END);
   string line = "CLOSE|" + IntegerToString((long)ticket) + "|" +
                 DoubleToString(price, 5) + "|" +
                 IntegerToString((long)t) + "|" +
                 DoubleToString(profit, 2) + "|" +
                 reason + "\n";
   FileWriteString(h, line);
   FileClose(h);
}
