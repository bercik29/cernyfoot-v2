"""Auth forms. Per owner decision D3 there are deliberately NO password-strength
rules — any non-empty password is accepted; the login rate limit is the guardrail."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo


class LoginForm(FlaskForm):
    nickname = StringField("Prezývka", validators=[DataRequired(message="Zadaj prezývku.")])
    password = PasswordField("Heslo", validators=[DataRequired(message="Zadaj heslo.")])


class ClaimForm(FlaskForm):
    password = PasswordField(
        "Nové heslo", validators=[DataRequired(message="Heslo nemôže byť prázdne.")]
    )
    confirm = PasswordField(
        "Heslo znova",
        validators=[
            DataRequired(message="Zopakuj heslo."),
            EqualTo("password", message="Heslá sa nezhodujú."),
        ],
    )
