from django import forms

from .models import CustomerMessage, ItemComment, Items


class ItemForm(forms.ModelForm):
    item_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label='Price',
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-lg border border-stone-300 px-4 py-3 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/20',
            'min': 0,
            'step': '0.01',
        }),
    )

    class Meta:
        model = Items
        fields = ('item_name', 'item_desc', 'item_price', 'item_image')
        labels = {
            'item_name': 'Item name',
            'item_desc': 'Description',
            'item_price': 'Price',
            'item_image': 'Image',
        }
        widgets = {
            'item_name': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-stone-300 px-4 py-3 '
                'focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/20',
                'placeholder': 'e.g. Margherita Pizza',
            }),
            'item_desc': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-stone-300 px-4 py-3 focus:border-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-700/20',
                'rows': 4,
                'placeholder': 'Describe the menu item',
            }),
            'item_image': forms.ClearableFileInput(attrs={
                'class': 'block w-full text-sm text-stone-600 file:mr-4 file:rounded-lg file:border-0 file:bg-emerald-800 file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-emerald-900',
                'accept': 'image/*',
            }),
        }


class CustomerMessageForm(forms.ModelForm):
    class Meta:
        model = CustomerMessage
        fields = ('name', 'email', 'message')
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full rounded-lg border border-stone-300 px-3 py-2',
                'autocomplete': 'name',
                'maxlength': 100,
                'required': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full rounded-lg border border-stone-300 px-3 py-2',
                'autocomplete': 'email',
                'maxlength': 254,
                'required': True,
            }),
            'message': forms.Textarea(attrs={
                'class': 'w-full rounded-lg border border-stone-300 px-3 py-2',
                'rows': 4,
                'maxlength': 2000,
                'required': True,
            }),
        }


class ChatStartForm(forms.Form):
    name = forms.CharField(max_length=100)
    email = forms.EmailField()


class ChatMessageForm(forms.Form):
    message = forms.CharField(max_length=2000, strip=True)


class ItemCommentForm(forms.ModelForm):
    class Meta:
        model = ItemComment
        fields = ('message',)
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 4,
                'maxlength': 2000,
                'required': True,
                'class': 'w-full rounded-lg border border-stone-300 px-4 py-3 '
                'focus:border-emerald-700 focus:outline-none focus:ring-2 '
                'focus:ring-emerald-700/20',
                'placeholder': 'Share your thoughts about this item',
            }),
        }