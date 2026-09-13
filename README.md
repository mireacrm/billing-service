# Сервис биллинга

Отвечает за выставление счетов по завершённым записям, фиксацию оплаты
и расчёт комиссии специалистов.

Счёт создаётся асинхронно после получения события `appointment.completed`.
Для получения стоимости и других данных завершённой записи сервис обращается
по gRPC к `booking-service`.

После оплаты Billing Service запрашивает начисление баллов у `client-service`
и публикует событие `invoice.paid`.

## Возможности

Сервис предоставляет следующие методы:

| Метод | Назначение |
|---|---|
| `GET /invoices/{invoice_id}` | Получение счёта |
| `POST /invoices/{invoice_id}/pay` | Фиксация оплаты |
| `GET /branches/{branch_id}/invoices` | Получение счетов филиала |
| `GET /employees/{employee_id}/commission` | Расчёт комиссии специалиста за период |

При получении счетов филиала можно использовать параметры `status` и `limit`.
Для расчёта комиссии период задаётся параметрами `from` и `to`.

## Обработка завершённой записи

Billing Service подписан на событие:

```text
appointment.completed

## Зависимости

| Пакет | Роль |
|---|---|
| [`mirea-contracts`](https://github.com/mireacrm/contracts-py) | сообщения и стабы gRPC |
| [`mireacrm-common`](https://github.com/mireacrm/py-common) | настройки, метрики, трасса, ошибки, база, события, gRPC |

Оба приезжают из своих репозиториев по версии из `pyproject.toml`.
Версию контрактов называет сервис, а не обвяз: два прямых URL одного
пакета pip считает конфликтом.

## Локально

```
pip install -e ".[dev]"
python -m pytest tests/unit -q
python -m pytest tests/integration -q   # нужен Postgres
docker build -t billing-service .
```

Систему целиком поднимает [`mireacrm/deploy`](https://github.com/mireacrm/deploy).
