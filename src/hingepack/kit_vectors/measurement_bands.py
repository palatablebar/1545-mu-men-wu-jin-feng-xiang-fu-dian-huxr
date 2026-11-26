from dataclasses import replace
from statistics import mean, median
from collections import Counter
from math import fsum

from .contracts import FEATURE_NAMES, FEATURE_KEYS, RAW_KEYS


def current_credible_scans(vector):
    scan_count = vector.input_values[0]
    scan_repeat = vector.input_values[5]
    return float(scan_count-min(scan_repeat,scan_count))


def compare_credible_scans(training, target):
    usual_credible_scans = take_sample(training, current_credible_scans)
    recent_credible_scans = take_sample(target, current_credible_scans)
    if len(usual_credible_scans) < 4 or not recent_credible_scans:
        return {'作业量': '去重后的有效扫', '有效读数': len(recent_credible_scans), '判断': '参考不足'}
    anchor_credible_scans = median(usual_credible_scans)
    measured_credible_scans = median(recent_credible_scans)
    ordered_credible_scans = sorted(usual_credible_scans)
    low_credible_scans, high_credible_scans = ordered_credible_scans[len(ordered_credible_scans)//10], ordered_credible_scans[(len(ordered_credible_scans)*9)//10]
    change_credible_scans = measured_credible_scans-anchor_credible_scans
    outside_credible_scans = sum(value<low_credible_scans or value>high_credible_scans for value in recent_credible_scans)
    return {'作业量': '去重后的有效扫', '训练参考': round(anchor_credible_scans, 4), '现场中位': round(measured_credible_scans, 4),
            '变动': round(change_credible_scans, 4), '越界量': outside_credible_scans, '有效读数': len(recent_credible_scans)}


def current_extra_tags(vector):
    scan_count = vector.input_values[0]
    expected = vector.input_values[1]
    scan_repeat = vector.input_values[5]
    return float(scan_count-min(scan_repeat,scan_count)-expected)


def compare_extra_tags(training, target):
    usual_extra_tags = take_sample(training, current_extra_tags)
    recent_extra_tags = take_sample(target, current_extra_tags)
    if len(usual_extra_tags) < 4 or not recent_extra_tags:
        return {'作业量': '超额扫码', '有效读数': len(recent_extra_tags), '判断': '参考不足'}
    anchor_extra_tags = median(usual_extra_tags)
    measured_extra_tags = median(recent_extra_tags)
    ordered_extra_tags = sorted(usual_extra_tags)
    low_extra_tags, high_extra_tags = ordered_extra_tags[len(ordered_extra_tags)//10], ordered_extra_tags[(len(ordered_extra_tags)*9)//10]
    change_extra_tags = measured_extra_tags-anchor_extra_tags
    outside_extra_tags = sum(value<low_extra_tags or value>high_extra_tags for value in recent_extra_tags)
    return {'作业量': '超额扫码', '训练参考': round(anchor_extra_tags, 4), '现场中位': round(measured_extra_tags, 4),
            '变动': round(change_extra_tags, 4), '越界量': outside_extra_tags, '有效读数': len(recent_extra_tags)}


def current_expected_gap(vector):
    scan_count = vector.input_values[0]
    expected = vector.input_values[1]
    scan_repeat = vector.input_values[5]
    return float(max(0,expected-scan_count+scan_repeat))


def compare_expected_gap(training, target):
    usual_expected_gap = take_sample(training, current_expected_gap)
    recent_expected_gap = take_sample(target, current_expected_gap)
    if len(usual_expected_gap) < 4 or not recent_expected_gap:
        return {'作业量': '待确认配件', '有效读数': len(recent_expected_gap), '判断': '参考不足'}
    anchor_expected_gap = median(usual_expected_gap)
    measured_expected_gap = median(recent_expected_gap)
    ordered_expected_gap = sorted(usual_expected_gap)
    low_expected_gap, high_expected_gap = ordered_expected_gap[len(ordered_expected_gap)//10], ordered_expected_gap[(len(ordered_expected_gap)*9)//10]
    change_expected_gap = measured_expected_gap-anchor_expected_gap
    outside_expected_gap = sum(value<low_expected_gap or value>high_expected_gap for value in recent_expected_gap)
    return {'作业量': '待确认配件', '训练参考': round(anchor_expected_gap, 4), '现场中位': round(measured_expected_gap, 4),
            '变动': round(change_expected_gap, 4), '越界量': outside_expected_gap, '有效读数': len(recent_expected_gap)}


def current_weight_share(vector):
    mass_g = vector.input_values[2]
    variant = vector.input_values[3]
    return float(mass_g/max(1,variant+1))


def compare_weight_share(training, target):
    usual_weight_share = take_sample(training, current_weight_share)
    recent_weight_share = take_sample(target, current_weight_share)
    if len(usual_weight_share) < 4 or not recent_weight_share:
        return {'作业量': '非标件均摊重量', '有效读数': len(recent_weight_share), '判断': '参考不足'}
    anchor_weight_share = median(usual_weight_share)
    measured_weight_share = median(recent_weight_share)
    band_weight_share = max(1.0, abs(anchor_weight_share)*.2, median(abs(value-anchor_weight_share) for value in usual_weight_share))
    change_weight_share = (measured_weight_share-anchor_weight_share) / band_weight_share
    outside_weight_share = sum(abs(value-anchor_weight_share)>2.5*band_weight_share for value in recent_weight_share)
    return {'作业量': '非标件均摊重量', '训练参考': round(anchor_weight_share, 4), '现场中位': round(measured_weight_share, 4),
            '变动': round(change_weight_share, 4), '越界量': outside_weight_share, '有效读数': len(recent_weight_share)}


def current_repair_by_item(vector):
    expected = vector.input_values[1]
    partial = vector.input_values[4]
    return float(partial/expected)


def compare_repair_by_item(training, target):
    usual_repair_by_item = take_sample(training, current_repair_by_item)
    recent_repair_by_item = take_sample(target, current_repair_by_item)
    if len(usual_repair_by_item) < 4 or not recent_repair_by_item:
        return {'作业量': '补领单每件派生', '有效读数': len(recent_repair_by_item), '判断': '参考不足'}
    anchor_repair_by_item = median(usual_repair_by_item)
    measured_repair_by_item = median(recent_repair_by_item)
    ordered_repair_by_item = sorted(usual_repair_by_item)
    low_repair_by_item, high_repair_by_item = ordered_repair_by_item[len(ordered_repair_by_item)//10], ordered_repair_by_item[(len(ordered_repair_by_item)*9)//10]
    change_repair_by_item = measured_repair_by_item-anchor_repair_by_item
    outside_repair_by_item = sum(value<low_repair_by_item or value>high_repair_by_item for value in recent_repair_by_item)
    return {'作业量': '补领单每件派生', '训练参考': round(anchor_repair_by_item, 4), '现场中位': round(measured_repair_by_item, 4),
            '变动': round(change_repair_by_item, 4), '越界量': outside_repair_by_item, '有效读数': len(recent_repair_by_item)}


def current_redundant_rate(vector):
    scan_count = vector.input_values[0]
    scan_repeat = vector.input_values[5]
    return float(min(scan_repeat,scan_count)/scan_count)


def compare_redundant_rate(training, target):
    usual_redundant_rate = take_sample(training, current_redundant_rate)
    recent_redundant_rate = take_sample(target, current_redundant_rate)
    if len(usual_redundant_rate) < 4 or not recent_redundant_rate:
        return {'作业量': '重复扫密度', '有效读数': len(recent_redundant_rate), '判断': '参考不足'}
    anchor_redundant_rate = median(usual_redundant_rate)
    measured_redundant_rate = median(recent_redundant_rate)
    ordered_redundant_rate = sorted(usual_redundant_rate)
    low_redundant_rate, high_redundant_rate = ordered_redundant_rate[len(ordered_redundant_rate)//10], ordered_redundant_rate[(len(ordered_redundant_rate)*9)//10]
    change_redundant_rate = measured_redundant_rate-anchor_redundant_rate
    outside_redundant_rate = sum(value<low_redundant_rate or value>high_redundant_rate for value in recent_redundant_rate)
    return {'作业量': '重复扫密度', '训练参考': round(anchor_redundant_rate, 4), '现场中位': round(measured_redundant_rate, 4),
            '变动': round(change_redundant_rate, 4), '越界量': outside_redundant_rate, '有效读数': len(recent_redundant_rate)}


def current_remaining_kit(vector):
    expected = vector.input_values[1]
    variant = vector.input_values[3]
    return float(max(0,expected-variant))


def compare_remaining_kit(training, target):
    usual_remaining_kit = take_sample(training, current_remaining_kit)
    recent_remaining_kit = take_sample(target, current_remaining_kit)
    if len(usual_remaining_kit) < 4 or not recent_remaining_kit:
        return {'作业量': '常规剩余件数', '有效读数': len(recent_remaining_kit), '判断': '参考不足'}
    anchor_remaining_kit = median(usual_remaining_kit)
    measured_remaining_kit = median(recent_remaining_kit)
    ordered_remaining_kit = sorted(usual_remaining_kit)
    low_remaining_kit, high_remaining_kit = ordered_remaining_kit[len(ordered_remaining_kit)//10], ordered_remaining_kit[(len(ordered_remaining_kit)*9)//10]
    change_remaining_kit = measured_remaining_kit-anchor_remaining_kit
    outside_remaining_kit = sum(value<low_remaining_kit or value>high_remaining_kit for value in recent_remaining_kit)
    return {'作业量': '常规剩余件数', '训练参考': round(anchor_remaining_kit, 4), '现场中位': round(measured_remaining_kit, 4),
            '变动': round(change_remaining_kit, 4), '越界量': outside_remaining_kit, '有效读数': len(recent_remaining_kit)}


def current_warehouse_pressure(vector):
    mass_g = vector.input_values[2]
    partial = vector.input_values[4]
    return float(mass_g*(1+partial/10)/1000)


def compare_warehouse_pressure(training, target):
    usual_warehouse_pressure = take_sample(training, current_warehouse_pressure)
    recent_warehouse_pressure = take_sample(target, current_warehouse_pressure)
    if len(usual_warehouse_pressure) < 4 or not recent_warehouse_pressure:
        return {'作业量': '复点件重负荷', '有效读数': len(recent_warehouse_pressure), '判断': '参考不足'}
    anchor_warehouse_pressure = median(usual_warehouse_pressure)
    measured_warehouse_pressure = median(recent_warehouse_pressure)
    band_warehouse_pressure = max(1.0, abs(anchor_warehouse_pressure)*.2, median(abs(value-anchor_warehouse_pressure) for value in usual_warehouse_pressure))
    change_warehouse_pressure = (measured_warehouse_pressure-anchor_warehouse_pressure) / band_warehouse_pressure
    outside_warehouse_pressure = sum(abs(value-anchor_warehouse_pressure)>2.5*band_warehouse_pressure for value in recent_warehouse_pressure)
    return {'作业量': '复点件重负荷', '训练参考': round(anchor_warehouse_pressure, 4), '现场中位': round(measured_warehouse_pressure, 4),
            '变动': round(change_warehouse_pressure, 4), '越界量': outside_warehouse_pressure, '有效读数': len(recent_warehouse_pressure)}


def take_sample(vectors, measure):
    return tuple(measure(record) for record in vectors if not record.missing)


def measure_kit_vectors_band(history, daybook):
    yield compare_credible_scans(history, daybook)
    yield compare_extra_tags(history, daybook)
    yield compare_expected_gap(history, daybook)
    yield compare_weight_share(history, daybook)
    yield compare_repair_by_item(history, daybook)
    yield compare_redundant_rate(history, daybook)
    yield compare_remaining_kit(history, daybook)
    yield compare_warehouse_pressure(history, daybook)


def evaluate_shift(training, current):
    return list(measure_kit_vectors_band(training, current))
