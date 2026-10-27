export const strategyCatalog: Record<string, { name: string; features: string }> = {
  uniform: { name: '均匀随机基线', features: '等概率抽样，对照与回退策略' },
  frequency: { name: '单频率', features: '近100期频率＋向均匀概率平滑' },
  logistic: { name: '基础逻辑回归', features: '近30/100期频率、上期是否出现，正则化与概率校准' },
  freq_odd: { name: '频率＋奇偶', features: '基础特征＋奇偶组频率和上期奇偶结构' },
  freq_size: { name: '频率＋大小', features: '基础特征＋大小组频率和上期大小结构' },
  freq_thirds: { name: '频率＋三区', features: '基础特征＋三区频率和上期三区结构' },
  freq_prime: { name: '频率＋质合', features: '基础特征＋质数/合数组统计，1单列' },
  freq_omission: { name: '频率＋遗漏', features: '基础特征＋当前、最大、平均遗漏和最近已完成周期（300期窗口）' },
  freq_odd_omission: { name: '频率＋奇偶＋遗漏', features: '基础特征＋奇偶、遗漏及交互项' },
  freq_structure: { name: '频率＋组合结构', features: '基础特征＋奇偶、大小、三区、质合联合特征' },
  freq_numeric: { name: '频率＋数值特征', features: '基础特征＋上期和值、跨度、均值、AC、尾数和及交互项' },
  freq_association: { name: '频率＋关联特征', features: '基础特征＋重号、邻号、同尾及历史相邻/同尾/二码共现' },
  forest_all: { name: '全指标＋随机森林', features: '同全指标特征，64棵浅层树、单线程、时间顺序概率校准' },
  neural_all: { name: '全指标＋小型神经网络', features: '同全指标特征，单隐藏层16节点、L2正则、时间顺序概率校准' },
  freq_all: { name: '全指标联合', features: '基础特征＋遗漏、组合结构、数值和关联特征' },
};
export function strategyName(version: string) {
  return strategyCatalog[version.split('-v')[0]]?.name ?? version;
}
