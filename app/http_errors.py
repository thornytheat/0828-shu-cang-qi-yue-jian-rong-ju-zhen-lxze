from flask import jsonify

from app.business import DomainIssue

LABELS = {
    'FILE_TOO_LARGE':'文件超过 256 KiB', 'FILE_EMPTY':'文件没有内容', 'FILE_BLANK':'文件只有空白',
    'HEADER_ONLY':'文件只有标题行', 'HEADER_MISMATCH':'列名与字段字典不一致', 'ENCODING_INVALID':'请使用 UTF-8 CSV',
    'CSV_MALFORMED':'CSV 引号或行格式异常', 'ROW_LIMIT':'文件超过 2000 行', 'FILE_REQUIRED':'请选择 CSV 文件',
    'RUN_NOT_FOUND':'批次不存在', 'REVIEW_FIELDS':'请填写 3 至 200 字复核意见', 'STALE_REVIEW':'批次已更新，请刷新',
    'RUN_FINALIZED':'批次已签发', 'UNRESOLVED_ISSUES':'存在待处理差异', 'SAMPLE_UNKNOWN':'样例不存在', 'STAGE_UNKNOWN':'处理阶段不存在',
    'TABLE_NOT_FOUND':'表不存在', 'WRITE_VERSION_NOT_FOUND':'候选写版本不存在', 'READ_VERSION_NOT_FOUND':'在用读版本不存在',
    'CHECK_NOT_FOUND':'尚未核对或核对结论已不存在', 'BATCH_NOT_FOUND':'签发批次不存在',
    'STALE_CHECK':'读版本已变化，原核对结论失效，请重新核对',
    'WRITE_VERSION_CONFLICT':'同表已有其他候选写版本先生效',
    'RELEASE_FIELDS':'表版本或字段定义无效',
}


def response(error):
    code = error.code
    not_found = {
        'RUN_NOT_FOUND', 'SAMPLE_UNKNOWN', 'STAGE_UNKNOWN', 'TABLE_NOT_FOUND',
        'WRITE_VERSION_NOT_FOUND', 'READ_VERSION_NOT_FOUND', 'CHECK_NOT_FOUND', 'BATCH_NOT_FOUND',
    }
    conflicts = {
        'STALE_REVIEW', 'RUN_FINALIZED', 'UNRESOLVED_ISSUES', 'STALE_CHECK',
        'WRITE_VERSION_CONFLICT', 'RELEASE_CONFLICT',
    }
    status = 404 if code in not_found else 409 if code in conflicts else 413 if code=='FILE_TOO_LARGE' else 422
    return jsonify(code=code,message=LABELS.get(code,code)),status
