# WQ 社区 Alpha 模板合集（顾问社区贴）

> **来源**：WorldQuant BRAIN 社区帖子《可以尝试使用的Alpha模板》（Pinned）
> **帖子 ID**：26054361848343
> **作者**：WL13229
> **抓取/整理日期**：2026-09-03
> **原始链接**：https://support.worldquantbrain.com/hc/en-us/community/posts/26054361848343-可以尝试使用的Alpha模板
> **保存方式**：由用户从页面复制后逐字保存，供后续 alpha 研究复用。请以 WQ BRAIN 平台实际语法为准。

## 作者原文声明

请注意，本贴仅收集总结，优秀程度不一定。
部分存在严重overfitting风险，请参加更多顾问活动及课程解锁insight。

## 使用提示（本文件附加）

- 帖子中的多行表达式用行尾 `\` 续行，粘贴进 BRAIN 时请**合并成单行**。
- `{data}` / `{Fundamental}` / `{Analyst Std}` / `{OptionHighPrice}` / `{datafield}` / `{i}` / `{j}` / `{sell_order}` / `{buy_order}` 等为**占位符**，需替换成实际 datafield 或具体字段。
- `<ts_opr_1>` / `<group_opr>` / `<vector_opr>` / `<pv_field>` / `<vol_field>` / `<grouping>` / `<days1>` / `<days2>` / `<group_compare_op>` 等为**模板骨架参数**，按说明替换。
- 文中 `Decay设置为10，Neutralize设置为industry`、`TOP3000 INDUSTRY DECAY 60 30`、`# CHN模板` 等为回测设置或区域说明。
- 作者注明：部分 insight 需参加顾问活动/课程解锁；财务数据类模板建议从盈利成长、成本、经营、安全性等维度搜索，且需注意口径问题与数据及时利用问题。

---

## 模板正文（用户原贴，逐字保存）

```text
regression_neut(regression_neut(group_neutralize(group_zscore(\
vec_avg({data}),sector),bucket(rank(cap),range="0.1,1,0.1")),\
group_neutralize(group_zscore(cap,sector),bucket(rank(cap),range="0.1,1,0.1"))),\
ts_ir(returns-group_median(returns,sector),126))
fear = ts_mean(abs(returns - group_mean(returns,1,market))/(abs(returns)+abs(group_mean(returns,1,market))+0.1),20);\
-group_neutralize(fear*group_normalize(ts_decay_exp_window(ts_percentage(vec_count(rsk82_raw_m3g_tni_p_su_fte),60,percentage=0.9)\
-ts_percentage(vec_count({data}),60,percentage=0.1),20, factor=0.8),market)*inverse(abs(ts_entropy(volume,20)))\
,bucket(rank(cap),range="0.1,1,0.1"))
d1_level=ts_max(vec_stddev({data}),20);\
d1_stability=ts_kurtosis(vec_stddev({data}),20);\
mkt_level=group_min(d1_stability,industry);\
-group_neutralize(d1_stability<=mkt_level?-d1_level:d1_level,bucket(rank(cap),range="0.1,1,0.1"))
group = bucket(rank(cap),range='0.1,1,0.1');

risk = rank(-ts_av_diff(vec_min({Analyst Std}),360));

alpha=rank((1-risk)*group_rank(ts_scale(vec_max({OptionHighPrice})/close,120),industry));

group_neutralize(ts_mean(alpha,2),group)
Decay设置为10，Neutralize设置为industry
my_group = market;

my_group2 = bucket(rank(cap),range='0,1,0.1');

alpha=rank(group_rank(ts_decay_linear(volume/ts_sum(volume,252),10),my_group)*group_rank(ts_rank(vec_avg({Fundamental})),my_group)*group_rank(-ts_delta(close,5),my_group));

trade_when(volume>adv20,group_neutralize(alpha,my_group2),-1)
market_return = group_mean(returns,1,market);

fear = ts_mean(abs(returns - market_return)/(abs(returns)+abs(market_return)),20);

vhat = ts_regression(volume,ts_mean(vec_avg({Sentiment}),5),120);

ehat = ts_regression(returns-market_return,vhat,120);

alpha = group_neutralize(-ehat*rank(fear),bucket(rank(cap),range='0,1,0.1'));

trade_when(abs(returns)<0.075,regression_neut(alpha,volume),abs(returns)>0.1)
Decay设置为20，Neutralize设置为industry
vector_neut(group_neutralize(group_neutralize(ts_arg_max(vec_norm({datafield}), 220),bucket(rank(assets), range="0.1,1,0.1")),subindustry), group_normalize(ts_delay(cap, 220),subindustry))
sentiment = ts_backfill(ts_delay( vec_avg(SENTIMENT FROME OTHER),1),20)

vhat=ts_regression(volume,sentiment,250); 

ehat=-ts_regression(returns,vhat,750); 1

alpha=group_rank(ehat,bucket(rank(cap),range='0,0.1,0.1'))
IR = abs(ts_mean(returns,252)/ts_std_dev(returns,252));      
 
regression_neut ( vector_neut (ts_zscore( vec_max (ANALYST)/close, 126),ts_median(cap, 126) ),IR)
small_sell = vec_sum(SPECIAL SELL ORDER);

small_buy = vec_sum(SPECIAL BUY ORDER);

fac = - small_sell - small_buy;

fac_diff_mean = power(rank(fac - group_mean(fac, 1, subindustry)),D);

IR = abs(ts_mean(returns,126)/ts_std_dev(returns,126));

group_neutralize(regression_neut(group_neutralize(fac_diff_mean,bucket(rank(cap), range='-0.1,1,0.1')),IR),sta1_top3000c10)
trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9,-regression_neut(group_neutralize(ts_std_dev(vec_avg(volatility),20)/ ts_mean(vec_avg(volatility),20),bucket(rank(assets),range = '0,1,0.1')),ts_std_dev(returns,30))+group_neutralize(-ts_std_dev(vec_avg(volume)/sharesout,30)/ ts_mean(vec_avg(volume)/sharesout,30),bucket(rank(cap), range = '0,1,0.1')),-1)
e = power(group_rank(-ts_decay_exp_window(ts_sum(if_else(vwap-group_mean(vwap,1,industry)-0.01>0,1,0)*ts_corr((log(volume/sharesout)),cap,5),5),20),industry),3);
trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9,e,-1)
vector_neut(power(rank(group_neutralize(-ts_decay_exp_window(ts_sum(if_else((alpha)-group_mean((alpha),1,bucket(rank(assets),range = '0,1,0.1'))-0.02>0,1,0)*ts_co_kurtosis(vec_sum(turnover),cap,5),3)/3,50),industry)),2),assets)
signal = ts_rank(vec_stddev{fnd}, 60);
signal_str = group_rank(signal, bucket(rank(cap), range='0.1,1,0.2'));
pv_info = ts_rank(close, 60);
pv_info_str = group_neutralize(close, bucket(rank(cap), range='0.1,1,0.2'));
IR = abs(ts_mean(returns,126)/ts_std_dev(returns,126));;
rank(vector_neut(vector_neut(signal_str, pv_info_str),IR))
market_pv = group_mean(adv20,1,market);
modified = vec_avg(anl);
short_term_excess_return = ts_mean(pv-market_pv,5);
long_term_excess_return = ts_delay(ts_mean(pv-market_pv,120),120);
parf = regression_neut(regression_neut(modified,short_term_excess_return),long_term_excess_return);
group_zscore(parf,subindustry)
piece_1 = group_mean(vec_stddev(anl) , 1 , subindustry) - vec_stddev(anl)
time_mean(piece_1, 60)
{ts_opr_1}({group_opr}(ts_opr_2(rank({vector_opr}({pv_field})),rank({vector_opr}({vol_field})),{days1}),{grouping}){,days2})
market_returns = group_mean(returns,cap,market);
modified = vec_sum(Analyst);
short_term_excess_return = ts_mean(returns-market_returns,5);
long_term_excess_return = ts_delay(ts_mean(returns-market_returns,20),20);
parf = regression_neut(regression_neut(modified,short_term_excess_return),long_term_excess_return);
trade_when(ts_rank(ts_std_dev(market_returns,10),252)<0.9,group_neutralize(parf,bucket(rank(cap),range='0,1,0.1')),-1)
my_group=bucket(rank(cap),range='0,1,0.1');
Alpha=group_rank(ts_decay_linear(volume/ts_sum(volume,252),20),my_group)*group_rank(ts_co_kurtosis(news_data,returns,252),my_group)*group_rank(-ts_delta(close,5),my_group)
a = ts_zscore({datafield, 252);a1 = group_neutralize(a, bucket(rank(cap), range='0.1,1,0.1'));a2 = group_neutralize(a1, industry);b = ts_zscore(cap, 252);b1 = group_neutralize(b, industry);c = regression_neut(a2,b1);c
group_neutralize(ts_co_skewness(rp_nip_inverstor,ts_co_skewness(vec_max(nws18_qep),rp_css_ratings,225),225),bucket(rank(beta_last_30_days_spy), range="0,1,0.1"))
regression_neut(vector_neut(ts_rank(vec_max({ANALYST})/close,120),ts_median(cap, 120) ),abs(ts_mean({RETURNS},252)/ts_std_dev({RETURNS},252)))
small_sell = vec_sum({sell_order});
small_buy = vec_sum({buy_order});
fac = small_sell - small_buy;
fac_diff_mean = power(rank(fac - group_mean(fac, 1, subindustry)),{days});
IR = abs(ts_mean(returns,126)/ts_std_dev(returns,126));
group_neutralize(regression_neut(group_neutralize(fac_diff_mean,bucket(rank(cap), range='-0.1,1,0.1')),IR),sta1_top3000c10)
roa = group_zscore(fnd72_s_pit_or_cf_q_cf_net_inc*2/(assets+last_diff_value(assets,300)),sector);

pb = group_zscore(mdl175_bp,sector);

ITR = group_zscore(inventory_turnover,sector);

DtA = group_zscore(mdl175_debtsassetratio,sector);

WAtA = group_zscore(mdl175_workingcapital/assets,sector);

NAYOY = group_zscore(mdl175_netassetgrowrate,sector);

int2A = group_zscore(mdl175_intangibleassetratio,sector);

rank(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(regression_neut(roa,pb),ITR),DtA),WAtA),NAYOY),int2A),log(cap)))
<Arithmetich_or Transformational_op>(<ts_compare_op>(<Company Fundamental Data for Equity>， <Price Volume Data for Equity>， <days>)*<Company Fundamental Data for Equity>)
系列1
A = sign(finance_var)*log(abs(finance_var)+1));

B = sign(finance_var)*log(abs(finance_var)+1));

regression_neut(A,B)
系列2
ts_regression (ts_zscore(A,500), ts_zscore(B,500),500)
系列3
1/ts_std_dev(ts_regression (ts_zscore(A,500), ts_zscore(B,500),500)，500)
系列4
residual = ts_regression (ts_zscore(A,500), ts_zscore(B,500),500);

residual/ts_std_dev(residual ，500)
系列5
ts_regression (ts_zscore(A,500), timestep(500),500);
上述5个系列后续可以尝试同时结合截面回归和时序回归。通过截面回归处理财务数据的分布，通过时序回归找出robust的signal
缩小space。上述财务数据并没用限制，因此空间非常大；建议从盈利成长、成本、经营、安全性等重要维度先进行搜索，另外，可以先不考虑覆盖率较低的datafield
可以用分析师数据代替财务数据，比如净利润
基本面量化建议从经济逻辑出发，也不建议使用很复杂的公式，容易overfitting（因为数据点较少，很容易fit噪音）
注意窗口设置时的500天，这实际上会导致回归时变量的方差被低估
注意口径问题/数据及时利用问题。口径问题是指：在财报发布的月份中，比如4月，A公司比B公司先发，此时B公司还是t-1期的财务数据，而A公司是t期的财务数据，由于Brain是日频调仓，可能不具备可比性；但如果不及时利用数据，收益也会被其他交易者兑现，因此需要权衡。但大多数情况下，口径问题<<<<<<<<数据及时利用问题，因此该问题建议注意而不是规避
在计量经济学中，还有“互为因果”的问题，我对这个问题的了解没有那么深入，不过直觉上很好理解。我们拿到的财务数据，是静态的，也就是说，我们不清楚这样的财务数据是如何形成的。例如成本越高，收益越高，互为因果现象会是：成本越高，我的收益理应变高，收益变高，我就会更激进地投入生产，提高成本，这也会导致估计量有误。传统的解决方法为引入额外的工具变量，在做alpha中，我们也许可以融合另类数据，比如财务附注中的语气，判断公司是激进扩张还是稳扎稳打，从而决定 变量在回归中的位置
shout out to YW93864
<group_compare_op>(
  <transform_op>(
    <logical_op>(
      greater(
        ts_zscore(<ts_compare_op>(<news_metric>, <days>), <lookback_days>),
        <threshold>
      ),
      ts_zscore(<news_metric>, <days>),
      <default_value>
    )
  ),
  <parameters>
), <group>
)

e.g
group_rank(
  filter(
    sigmoid(
      if_else(
        greater(ts_zscore(news_sentiment, 30), 1),
        ts_zscore(news_sentiment, 30),
        0
      )
    ),
    h="1 2 3 4",
    t="0.5"
  ),
  industry
)

tmp = (group_rank(fnd72_s_pit_or_cf_q_cf_cash_from_inv_act, sector) > 0.5) * 4 + (group_rank(fnd72_s_pit_or_cf_q_cf_cash_from_fnc_act, sector) > 0.5) * 2 + (group_rank(fnd72_s_pit_or_cf_q_cf_cash_from_oper, sector) > 0.5) * 1;

2 * (tmp == 1) - (tmp == 2) - (tmp == 6)
(((ts_rank(ts_backfill({i}, 30), 504) < 0.5) && (ts_rank(ts_backfill({j}, 30), 504) > 0.5)) ? ts_rank(ts_backfill({i}, 30), 504) : -ts_rank(ts_backfill({i}, 30), 504))
目前已在GLB测试了 {i} 和 {j} 都是 fundamental72 的情况。
power(ts_std_dev(abs(returns),30),2)-power(ts_std_dev(returns,30),2) 
IR = abs(ts_mean(returns,252)/ts_std_dev(returns,252));
r=returns;
a=power(ts_std_dev(abs(r)+r,30),2);
b=power(ts_std_dev((abs(r)-r),30),2);
c=regression_neut(b-a,IR);
group_neutralize(group_neutralize(c,bucket(rank(cap),range='0.2,1,0.2')),country)
- ts_delta(A, 3)，用于挖掘反转因子（时间参数可以根据dataset/datafield调整）。通过遍历pv1, model77两个dataset共计12+536=548个datafield，筛选只显示sharp>2的alpha

a = -ts_delta(datafield,3);

b=abs(ts_mean(returns,252)/ts_std_dev(returns,252));

group_neutralize(vector_neut(a,b),subindustry)
- A * ts_std_dev(A, 30)，我称其为“小而稳”（时间参数可根据Dataset/Datafield调整）。

a = - A * ts_std_dev(A, 20);

b=abs(ts_mean(returns,252)/ts_std_dev(returns,252));

vector_neut(a,b)
nss = ts_backfill(se_score,20);

processed_news_sentiment = (nss - ts_mean(nss,250))/ts_std_dev(nss,250);

monthly_returns = ts_ir(returns,20);

processed_returns = ts_backfill(monthly_returns, 20);

ranked_sentiment = ts_mean(group_rank(processed_news_sentiment,industry), 20);

ranked_returns = ts_mean(group_rank(-processed_returns,industry), 20);  // Negative to rank low returns higher

lrhs = add(ranked_sentiment, ranked_returns);  // Assuming delay mimics the holding until realization

hrls = add(inverse(ranked_sentiment), inverse(ranked_returns));  // Inverse to get the opposite characteristics

alpha = subtract(lrhs, hrls);

alpha

TOP3000 INDUSTRY DECAY 60 30
# day1
d1_mean = ts_mean(close/ts_delay(close, 1)-1,20);
d1_std = ts_std_dev(close/ts_delay(close, 1)-1,20);
d1_mkt_mean = group_mean(d1_std, 1, market);
d1_std_rev = d1_std<d1_mkt_mean?-d1_mean:d1_mean;
tnv = volume/(sharesout*1000000);
tnv_diff = ts_delta(tnv, 1);
mkt_tnv_mean = group_mean(tnv_diff, 1, market);
rev_return = tnv_diff<mkt_tnv_mean?-(returns): (returns);
d1_tnv_rev = ts_mean(rev_return, 20);
# dayo
do_return = close/open-1;
do_mean = ts_mean(d0_return, 20);
do_std = ts_std_dev(d0_return, 20);
do_mkt_mean = group_mean(d0_std, 1, market);
do_std_rev = d0_std<d0_mkt_mean?-d0_mean:d0_mean;
do_rev = tnv_diff<mkt_tnv_mean?- (do_return): (d0_return);
d0_tnv_rev = ts_mean(do_rev, 20);
# day night
night_ret = open/ts_delay(close, 1);
night_mkt_mean = group_mean(night_ret, 1, market);
night_dist = abs (night_ret - night_mkt_mean);
dist_mean = ts_mean(night_dist,20);
dist_std = ts_std_dev(night_dist,20);
night_mean = group_mean(dist_std, 1, market);
night_std_rev = dist_std<night_mean?-dist_mean:dist_mean;
delay_tnv_change = ts_delay(tnv_diff, 1);
delay_market_tnv_mean = group_mean(delay_tnv_change, 1, market);
tnv_dist = abs (delay_tnv_change-delay_market_tnv_mean);
tnv_dist_mkt_mean = group_mean(tnv_dist, 1, market);
night_reverse = tnv_dist<tnv_dist_mkt_mean?-night_dist:night_dist;
night_tnv_rev = ts_mean(night_reverse, 20);
ballteam_coin = -d1_std_rev-d1_tnv_rev-d0_std_rev-d0_tnv_rev-night_tnv_rev-night_std_rev;
group_neutralize(ballteam_coin,bucket(rank(cap),range='0.1,1,0.1'))
turnover = volume / sharesout;
avg_turn = ts_mean(turnover, 30);
nor_turn = ts_delay(turnover - avg_turn, 3);
change = (close - open) / open;
avg_change = ts_mean(change, 30);
nor_change = change - avg_change;
ts_corr(nor_turn, abs(nor_change), 10) 
triggerTradeexp = (ts_arg_min(volume, 5) > 3) || (volume >= ts_sum(volume, 5) / 5);
alphaexp = rank(rank((high + low) / 2 - close) * rank((mdl175_roediluted*mdl175_cashrateofsales)));
tradeExitexp = -1;  
trade_when(triggerTradeexp, alphaexp, tradeExitexp)
overnight_ret = (open - ts_delay(close,1))/ts_delay(close,1);
abs_ovn_ret = abs (overnight_ret);
turn = volume/sharesout;
turn_d1 = ts_delay(turn, 1);
corr = ts_corr (abs_ovn_ret, turn_d1,7);
-(corr)
Turn20_ = ts_mean(volume/sharesout, 20);
Turn20 = group_neutralize(Turn20_, bucket(rank(cap), range="0.1,1,0.1"));

STR_ = ts_std_dev(volume/sharesout, 20);
STR = group_neutralize(STR_, bucket(rank(cap), range="0.1,1,0.1"));

score2 = rank(- nan_mask(Turn20, if_else(rank(STR) < 0.5, 1, -1))) * 0.5;
score3 = rank(nan_mask(Turn20, if_else(rank(STR) >= 0.5, 1, -1))) * 0.5;

signal_ = add(rank(STR), score2, score3, filter = true);
signal = left_tail(rank(signal_), maximum=0.98);
- group_rank(signal, bucket(rank(cap), range="0.1,1,0.1"))
my_group=bucket(rank(cap), range="0,1,0.1");
shock=(high-ts_delay(low, 1))/ts_delay(low, 1);
talor_shock=(shock-log(shock+1))*2-log(shock+1)**2;
alpha=-group_rank(ts_mean(talor_shock, 24), my_group);
group_neutralize(alpha,my_group)
turnover_rank = ts_mean(rank(volume / (sharesout * 1000000)), 22);
spe = rank(vec_avg(anl17_d1_spe_tse));
bp = rank(vec_avg(anl17_d1_bp_tse));
alpha = spe - bp;
# alpha
turnover_rank > 0.1 ? alpha : 0
# CHN模板
turn = volume/sharesout ;
turn20 = rank(regression_neut(-ts_mean(turn,20),densify(cap)));
STR = regression_neut(-ts_std_dev(turn,20),densify(cap));
UTR = STR+ turn20 * (STR/(1+abs(STR)));
regression_neut(regression_neut(regression_neut(sign(UTR) * power(abs(UTR),0.
5),turn20),vwap),ts_delta(retained_earnings / sharesout, 120))
internal=ts_delay(ts_percentage(returns, 60, percentage=0.9)-ts_percentage
(returns, 60, percentage=0.1),40);
CV=ts_std_dev((close/open - 1), 20)/ts_mean((close/open - 1),20);
alpha=ts_sum(-returns,20)*rank(internal)*abs (1/CV);
group_neutralize (alpha, bucket(rank(cap), range='0.1,1,0.1'))
industry_open = group_mean(open, cap, subindustry);
industry_close = group_mean(close, cap, subindustry);
industry_high = group_mean(high, cap, subindustry);
industry_low = group_mean(low, cap, subindustry);

Trends = if_else(industry_close > ts_delay(industry_close, 40),
industry_close/ts_max(industry_high, 100), rank(industry_close/ts_min
(industry_low, 500))-1);
OTSM = ts_sum((industry_high-ts_delay(industry_close, 1)) / (ts_delay
(industry_close, 1)-industry_low+1), 90);
DTSM = ts_sum((industry_high-industry_open) / (industry_open-industry_low+1),
5);

TSM = rank(OTSM) + rank(DTSM);

rank(Trends) + rank(TSM)
small_sell = vec_avg(pv27_sell_value_small_order);
small_buy = vec_avg(pv27_buy_value_small_order);
large_sell = vec_avg(pv27_sell_value_exlarge_order);
large_buy = vec_avg(pv27_buy_value_exlarge_order);

fac_small = small_sell + small_buy;
fac_large = large_sell + large_buy;

fac_small_diff_mean = fac_small - group_mean(fac_small, 1, subindustry);
fac_large_diff_mean = fac_large - group_mean(fac_large, 1, subindustry);

factor = if_else(rank(cap)<0.05, fac_small_diff_mean, fac_large_diff_mean);
if_else(rank(factor) <0.45, rank(factor)*0.55, factor, -1)
```

---

## 快速索引（按主题归类，便于检索）

### 通用技术 / GLB
- `regression_neut` 双层中性 + `group_zscore` + `ts_ir` 风格（首行 `regression_neut(regression_neut(group_neutralize(...`)
- fear 情绪反转：`fear = ts_mean(abs(returns - group_mean(returns,1,market))/...` + `group_normalize`/`ts_entropy`
- 日内波动风格：`d1_level=ts_max(vec_stddev({data}),20)` / `d1_stability=ts_kurtosis(...)`
- 大小盘分层中性：`group = bucket(rank(cap),range='0.1,1,0.1')` + `risk=rank(-ts_av_diff(vec_min({Analyst Std}),360))`
- 三因子乘性：`alpha=rank(group_rank(ts_decay_linear(volume/ts_sum(volume,252),10),my_group)*group_rank(ts_rank(vec_avg({Fundamental})),my_group)*group_rank(-ts_delta(close,5),my_group))` + `trade_when(volume>adv20,...)`
- 情绪回归：`vhat=ts_regression(volume,sentiment,250)` / `ehat=ts_regression(returns,vhat,750)`
- 多层中性基本面：`roa/pb/ITR/DtA/WAtA/NAYOY/int2A` → `rank(regression_neut(...log(cap)))`
- 财务截面+时序回归 系列1–5（含 `ts_regression`/`residual`/`timestep`）
- 新闻情绪筛选骨架 `<group_compare_op>(...)` + e.g. `group_rank(filter(sigmoid(if_else(greater(ts_zscore(news_sentiment,30),1),...`
- 现金流三位编码：`tmp = (group_rank(...cf_cash_from_inv_act...) > 0.5)*4 + ...` → `2*(tmp==1)-(tmp==2)-(tmp==6)`
- 反转因子：`-ts_delta(A,3)`（遍历 pv1/model77 共 548 个 datafield）
- “小而稳”：`-A * ts_std_dev(A,30)`
- 新闻+收益配对：`nss=ts_backfill(se_score,20)` → `lrhs/hrls` 多空
- 日内/隔夜/晚间反转合成：`ballteam_coin = -d1_std_rev-...-night_std_rev`

### 模板骨架（占位符）
- `{ts_opr_1}({group_opr}(ts_opr_2(rank({vector_opr}({pv_field})),rank({vector_opr}({vol_field})),{days1}),{grouping}){,days2})`
- `<Arithmetich_or Transformational_op>(<ts_compare_op>(<Company Fundamental Data>, <Price Volume Data>, <days>)*<Company Fundamental Data>)`
- `<group_compare_op>(<transform_op>(<logical_op>(greater(ts_zscore(...),<threshold>), ts_zscore(...), <default_value>)), <parameters>), <group>`

### CHN 模板
- 换手率分层：`turn20 = rank(regression_neut(-ts_mean(turn,20),densify(cap)))` / `UTR` 合成
- 内部收益分层：`internal=ts_delay(ts_percentage(returns,60,percentage=0.9)-ts_percentage(returns,60,percentage=0.1),40)`
- 行业趋势/ turnover 风格：`Trends` / `OTSM` / `DTSM` / `TSM`
- 大/小单资金流：`fac_small` / `fac_large` → `factor=if_else(rank(cap)<0.05, fac_small_diff_mean, fac_large_diff_mean)`

### 用户补充：纯量价高频底盘（见文末独立章节）
- 日内振幅 `(high-low)/close` 替代 `ts_std_dev(returns,20)`（抗自相关）；`min(volume/adv20,5)` 缩尾防妖股；`rank()` 三因子对齐；`signed_power(group_rank(adv20,industry),2)` 流动性平方装甲。

### 作者方法论提醒（摘要）
- 系列1–5 财务数据回归：截面回归处理分布、时序回归找 robust signal；建议从盈利成长/成本/经营/安全性搜索，先不碰低覆盖率 datafield。
- 不建议用太复杂公式（易 overfitting）。
- 窗口 500 天会低估回归变量方差。
- 口径问题 <<< 数据及时利用问题，建议"注意而非规避"。
- 互为因果问题：可融合另类数据（如财务附注语气）判断变量在回归中的位置。
- shout out to YW93864。

---

## 用户补充模板：纯量价高频底盘（非原帖，用户 2026-09-03 分享）

> **来源**：本段由用户在 2026-09-03 补充分享，**非**原帖 26054361848343 内容。
> **类型**：纯量价（price/volume）高频底盘，蓝图架构伪代码，需转换为 WQ BRAIN 实际表达式后回测。
> **核心逻辑**：抛弃长周期均线（斩断自相关性），直接抓「当日多空分歧剧烈（日内振幅大）+ 主力资金异动（放量）+ 近期总体超跌」的标的。
> **回测设置建议**（按用户原述）：None 区域 / GLB 均可先试；最外层 `group_zscore` 中性到 `industry`；`signed_power` 平方流动性装甲作用于 `group_rank(adv20, industry)`。

### 公式伪代码（蓝图架构，原样保存）

```text
group_zscore(
    ts_decay_linear(
        rank((high - low) / close) +
        rank(min(volume / adv20, 5)) -
        rank(returns),
    3),
industry) * signed_power(group_rank(adv20, industry), 2)
```

### 底层逻辑解剖（用户原述）

- **替换分母（天然抗黏滞）**：放弃常用的 `ts_std_dev(returns, 20)`，改用 `(high - low) / close`（真实日内振幅）。信号每一天都是全新且独立的，从根本上免疫高自相关性。
- **缩尾保护**：`min(..., 5)` 是防妖股利器，保住单笔胜率。
- **完美对齐**：全员套 `rank()`，振幅、成交量、收益率三分天下，绝对不发生量纲吞噬。
- **终极装甲**：最外层 `signed_power(group_rank(...), 2)` 平方流动性装甲，强迫系统把省下来的换手率集中在流动性绝对龙头身上，大幅降低摩擦成本。

### 转换为 BRAIN 实际表达式的注意点

- `signed_power` 在 BRAIN 中需用 `sign(x)*power(abs(x), p)` 替代，即：
  `sign(group_rank(adv20,industry))*power(abs(group_rank(adv20,industry)),2)`
- `min(volume/adv20, 5)` 中 `adv20` 若未作为内置字段可用，需以 `ts_sum(volume,20)` 等替代；`min(a, 5)` 在 BRAIN 中可用 `if_else(a>5, 5, a)` 或 `rank` 后截断实现。
- `ts_decay_linear(..., 3)` 的 `3` 为 decay 窗口，可按区域/数据频率微调。
- 多行缩进需合并为单行后再提交。
