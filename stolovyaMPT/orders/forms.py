from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, MenuItem

class CustomerRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'invalid': 'Введите допустимое имя пользователя. Оно может содержать только буквы, цифры и символы @/./+/-/_.',
            'unique': 'Пользователь с таким именем уже существует.',
        }
        self.fields['email'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'invalid': 'Введите корректный email адрес.',
        }
        self.fields['password1'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'password_too_short': 'Пароль должен содержать как минимум 8 символов.',
            'password_too_common': 'Пароль не должен быть слишком простым и распространенным.',
            'password_too_similar': 'Пароль не должен быть слишком похож на другую вашу личную информацию.',
            'password_entirely_numeric': 'Пароль не может состоять только из цифр.',
        }
        self.fields['password2'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'password_mismatch': 'Введенные пароли не совпадают.',
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.user_type = 'customer'
        if commit:
            user.save()
        return user

class CustomUserForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'user_type', 'password1', 'password2')
        widgets = {
            'user_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_type'].label = 'Роль пользователя'
        self.fields['user_type'].choices = [
            ('customer', 'Покупатель'),
            ('canteen_admin', 'Админ столовой'),
            ('db_admin', 'Админ БД'),
            ('tech_support', 'Техническая поддержка'),
        ]
        self.fields['username'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'invalid': 'Введите допустимое имя пользователя. Оно может содержать только буквы, цифры и символы @/./+/-/_.',
            'unique': 'Пользователь с таким именем уже существует.',
        }
        self.fields['email'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'invalid': 'Введите корректный email адрес.',
        }
        self.fields['password1'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'password_too_short': 'Пароль должен содержать как минимум 8 символов.',
            'password_too_common': 'Пароль не должен быть слишком простым и распространенным.',
            'password_too_similar': 'Пароль не должен быть слишком похож на другую вашу личную информацию.',
            'password_entirely_numeric': 'Пароль не может состоять только из цифр.',
        }
        self.fields['password2'].error_messages = {
            'required': 'Это поле обязательно для заполнения.',
            'password_mismatch': 'Введенные пароли не совпадают.',
        }

class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(
        label='Новый email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Введите новый email'})
    )
    password = forms.CharField(
        label='Пароль для подтверждения',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Введите текущий пароль'})
    )
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_new_email(self):
        new_email = self.cleaned_data.get('new_email')
        
        if new_email == self.user.email:
            raise forms.ValidationError('Новый email должен отличаться от текущего.')
        
        if CustomUser.objects.filter(email=new_email).exists():
            raise forms.ValidationError('Этот email уже используется другим пользователем.')
        
        return new_email
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.user.check_password(password):
            raise forms.ValidationError('Неверный пароль.')
        return password

class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['name', 'description', 'price', 'stock', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }