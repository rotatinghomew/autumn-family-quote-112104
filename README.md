# 亲子线路的预约价格兑现风险与书面报价

旅行顾问使用家庭行程需求、报价及库存凭据签发保价。金额为含税元，时刻为当地一天内。

## 资料交换

`data/samples.json` 是合成样册。`fields` 给出有序列名，`rows` 按该顺序记录数据，`meaning` 标明单位或来源区别。没有填写的值用 `null` 表示。

- `families`：flexible_time 为家庭接受的额外改时分钟。 列：`family`, `adults`, `children`, `start`, `end`, `budget`, `flexible_time`。
- `products`：从参观站到实践站的最短通行时间。 列：`slot`, `station`, `start`, `end`, `travel_to_next_min`。
- `offers`：人数为组合允许的上限；报价为整组合。 列：`offer`, `slot`, `adults`, `children`, `base`, `required_fee`, `expires`, `certainty`。
- `inventory`：库存为可供购买家庭组合数，ambiguous 是尚未承认的额外组合。 列：`slot`, `seq`, `confirmed`, `ambiguous`。
- `quotes`：options 里的每项是完整备选；locked 记录实际确认的一项。 列：`quote`, `family`, `options`, `locked`, `promised`, `accepted`, `seq`。
- `authority`：同一轮签发及救济共用的补差预算。 列：`seq`, `compensation_limit`。

## 检视

使用 Python 3.11，资料读取不依赖第三方包。

```sh
python3 source_book.py data/samples.json
python3 -m unittest -v
```

资料读取命令列出各表记录数；测试检查交叉引用与格式，不生成分析结果。
