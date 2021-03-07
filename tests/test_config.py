from paradox.config import config as cfg, get_limits_for_type

def test_get_limits_for_type_for_auto(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": 'auto',
        }
    )


    assert get_limits_for_type('partition') == None
    assert get_limits_for_type('partition', []) == []


def test_get_limits_for_type_for_specified_string_range(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": '1-4',
        }
    )


    assert get_limits_for_type('partition') == [1,2,3,4]
    assert get_limits_for_type('partition', []) == [1,2,3,4]


def test_get_limits_for_type_for_specified_string_list(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": '1,4',
        }
    )


    assert get_limits_for_type('partition') == [1,4]
    assert get_limits_for_type('partition', []) == [1,4]


def test_get_limits_for_type_for_specified_py_range(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": range(1,5),
        }
    )


    assert get_limits_for_type('partition') == [1,2,3,4]
    assert get_limits_for_type('partition', []) == [1,2,3,4]


def test_get_limits_for_type_for_specified_py_list(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            "partition": [1,2],
        }
    )


    assert get_limits_for_type('partition') == [1,2]
    assert get_limits_for_type('partition', []) == [1,2]


def test_get_limits_for_type_for_specified_py_None(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={}
    )


    assert get_limits_for_type('partition') == None
    assert get_limits_for_type('partition', []) == []


def test_get_limits_for_type_for_specified_empty_string(mocker):
    mocker.patch.multiple(
        cfg,
        LIMITS={
            'partition': ''
        }
    )


    assert get_limits_for_type('partition') == []
    assert get_limits_for_type('partition', [1,2]) == []