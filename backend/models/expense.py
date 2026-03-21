from datetime import datetime
from typing import Optional
from bson import ObjectId

class Expense:
    def __init__(
        self,
        date: str,
        category: str,
        amount: float,
        currency: str,
        payment_method: str,
        krw_amount: float,
        description: str,
        payer: str,
        receipt_image: Optional[str] = None,
        is_personal_expense: bool = False,
        personal_expense_for: Optional[str] = None,
        exchange_rate: Optional[float] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None
    ):
        self._id = _id
        self.date = date
        self.category = category
        self.amount = amount
        self.currency = currency
        self.payment_method = payment_method
        self.krw_amount = krw_amount
        self.description = description
        self.payer = payer
        self.receipt_image = receipt_image
        self.is_personal_expense = is_personal_expense
        self.personal_expense_for = personal_expense_for
        self.exchange_rate = exchange_rate
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> dict:
        data = {
            'date': self.date,
            'category': self.category,
            'amount': self.amount,
            'currency': self.currency,
            'payment_method': self.payment_method,
            'krw_amount': self.krw_amount,
            'exchange_rate': self.exchange_rate,
            'description': self.description,
            'payer': self.payer,
            'receipt_image': self.receipt_image,
            'is_personal_expense': self.is_personal_expense,
            'personal_expense_for': self.personal_expense_for,
            'created_at': self.created_at
        }
        if self._id:
            data['_id'] = str(self._id)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Expense':
        return cls(
            _id=data.get('_id'),
            date=data.get('date', ''),
            category=data.get('category', '기타'),
            amount=data.get('amount', 0),
            currency=data.get('currency', 'KRW'),
            payment_method=data.get('payment_method', '현금'),
            krw_amount=data.get('krw_amount', 0),
            exchange_rate=data.get('exchange_rate'),
            description=data.get('description', ''),
            payer=data.get('payer', ''),
            receipt_image=data.get('receipt_image'),
            is_personal_expense=data.get('is_personal_expense', False),
            personal_expense_for=data.get('personal_expense_for'),
            created_at=data.get('created_at')
        )
