from core.logger import get_logger, setup_logger


def test_setup_logger_does_not_raise():
    setup_logger()  # первый вызов
    setup_logger()  # повторный вызов не должен падать


def test_get_logger_returns_bound_logger():
    log = get_logger("ТестМодуль")
    assert log is not None


def test_get_logger_different_names():
    log1 = get_logger("Модуль1")
    log2 = get_logger("Модуль2")
    # оба работают без ошибок
    log1.debug("тест debug")
    log2.info("тест info")


def test_logger_can_log_russian():
    log = get_logger("РусскийМодуль")
    log.info("Всё работает нормально")
    log.warning("Предупреждение")
    log.error("Ошибка тестовая")
