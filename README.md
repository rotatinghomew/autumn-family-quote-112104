# 亲子线路的预约价格兑现风险与书面报价

旅行顾问使用家庭行程需求、报价及库存凭据签发保价。金额为含税元，时刻为当地一天内。
`quoting/` 是按轮次（seq）工作的报价兑现引擎：核对报价适用性、联合安置已受理保价、
估计同批需求竞争下能真正兑现的整程支出分布，并为客服区分不同结论。

## 资料交换

`data/samples.json` 是合成样册。`fields` 给出有序列名，`rows` 按该顺序记录数据，`meaning` 标明单位或来源区别。没有填写的值用 `null` 表示。

- `families`：flexible_time 为家庭接受的额外改时分钟。 列：`family`, `adults`, `children`, `start`, `end`, `budget`, `flexible_time`。
- `products`：从参观站到实践站的最短通行时间。 列：`slot`, `station`, `start`, `end`, `travel_to_next_min`。
- `offers`：人数为组合允许的上限；报价为整组合。 列：`offer`, `slot`, `adults`, `children`, `base`, `required_fee`, `expires`, `certainty`。
- `inventory`：库存为可供购买家庭组合数，ambiguous 是尚未承认的额外组合。 列：`slot`, `seq`, `confirmed`, `ambiguous`。
- `quotes`：options 里的每项是完整备选；locked 记录实际确认的一项。 列：`quote`, `family`, `options`, `locked`, `promised`, `accepted`, `seq`。
- `authority`：同一轮签发及救济共用的补差预算。 列：`seq`, `compensation_limit`。

## 语义约定

- 轮次（seq）是资料的时间轴。报价在 `seq <= expires` 时有效；库存取每个场次不晚于该轮的最新记录，确认数较上一轮减少即为外部撤回；补差预算取不晚于该轮的最新限额。
- 整程组合必须每站各选一个场次、互不重叠；家庭的 flexible_time 是总共可动用的改时分钟，同时覆盖早于窗口、晚于窗口与站间通行不足的分钟数。
- 报价总价为 `base + required_fee`（整组合、含税）。只有 `可订` 且未过期的报价可以进入可承诺价格；`仅询价` 报价与未承认库存只作参考，不当作确定可购。
- 已受理保价优先占用库存与补差预算。库存撤回或报价过期时，在该家庭明确接受范围（已受理报价的各备选）内联合改派；改派后实付超出承诺的差额由运营承担并计入本轮补差预算，家庭应付不超过承诺价。同一家庭接受前的多个备选只按一份需求核对，不会同时扣掉多个名额。
- 联合安置按最受限家庭优先做完备搜索：只要整体存在可行安置，就不会因为逐单改换让灵活家庭先占走唯一可用的场次。
- 日历页低价合计（每站最低适用报价直接相加）不核时段、库存与可订性，只作对照诊断，不能当作预计支出。

## 用法

使用 Python 3.11，资料读取不依赖第三方包。

```sh
python3 source_book.py data/samples.json            # 列出各表记录数
python3 -m quoting inventory data/samples.json --seq 3   # 库存与撤回
python3 -m quoting report data/samples.json --seq 3      # 整批兑现评估
python3 -m quoting service data/samples.json --seq 3 --family h3   # 客服查询
python3 -m quoting issue data/samples.json --seq 1 --family h4 \
    --option o2,o4 --promised 380 --out round1.json      # 签发保价并回写新资料
python3 -m unittest discover -s tests -v
```

- `report` 给出每个家庭的状态（已有保证 / 可承诺 / 证据不足 / 暂不成交 / 确定超预算）、
  典型支出分布、敏感约束与人工处理清单。
- `service` 为客服区分典型支出、目前可承诺的价格、家长已拿到的保证和需要重新联系的原因。
- `issue` 只在授权与可兑现条件同时成立时出具有期限的书面保价；`--out` 写出的资料文件
  可直接用于后续轮次报价。后续团期只需按格式追加 offers、inventory、authority 行，
  再用新的 `--seq` 运行即可。
