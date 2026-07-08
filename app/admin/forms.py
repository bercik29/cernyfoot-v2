"""Admin forms: seasons and holidays."""
from datetime import time

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, TimeField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

WEEKDAYS = [
    ("0", "Pondelok"),
    ("1", "Utorok"),
    ("2", "Streda"),
    ("3", "Štvrtok"),
    ("4", "Piatok"),
    ("5", "Sobota"),
    ("6", "Nedeľa"),
]


class SeasonForm(FlaskForm):
    label = StringField("Označenie (napr. 2026/2027)", validators=[DataRequired(), Length(max=20)])
    starts_on = DateField("Začiatok", validators=[DataRequired()])
    ends_on = DateField("Koniec", validators=[DataRequired()])
    match_weekday = SelectField("Hrací deň", choices=WEEKDAYS, default="3")
    match_start = TimeField("Začiatok zápasu", default=time(19, 0))
    match_end = TimeField("Koniec zápasu", default=time(20, 0))

    def validate_ends_on(self, field):
        if self.starts_on.data and field.data and field.data <= self.starts_on.data:
            raise ValidationError("Koniec sezóny musí byť po jej začiatku.")


class HolidayForm(FlaskForm):
    date_from = DateField("Od", validators=[DataRequired()])
    date_to = DateField("Do", validators=[DataRequired()])
    kind = SelectField(
        "Typ", choices=[("public", "Štátny sviatok"), ("school", "Školské prázdniny")]
    )
    description = StringField("Popis", validators=[Optional(), Length(max=200)])

    def validate_date_to(self, field):
        if self.date_from.data and field.data and field.data < self.date_from.data:
            raise ValidationError("Koniec musí byť rovnaký alebo po začiatku.")
