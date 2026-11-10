(() => {
    const rating = document.getElementById('item-rating');
    const description = document.getElementById('rating-description');
    if (!rating || !description) return;

    const stars = [...rating.querySelectorAll('[data-rating-star]')];
    const choices = [...rating.querySelectorAll('input[name="score"]')];
    let selectedScore = Number(rating.dataset.initialRating) || 0;

    function render(score) {
        for (const star of stars) {
            const isActive = Number(star.dataset.ratingStar) <= score;
            star.classList.toggle('text-amber-500', isActive);
            star.classList.toggle('text-stone-300', !isActive);
        }

        const selectedChoice = choices.find(
            (choice) => Number(choice.value) === score,
        );
        description.textContent = selectedChoice
            ? selectedChoice.getAttribute('aria-label').replace(/^\d+ stars: /, '')
            : 'Choose a star rating';
    }

    for (const star of stars) {
        star.addEventListener('mouseenter', () => {
            render(Number(star.dataset.ratingStar));
        });
    }

    for (const choice of choices) {
        choice.addEventListener('focus', () => render(Number(choice.value)));
        choice.addEventListener('change', () => {
            selectedScore = Number(choice.value);
            render(selectedScore);
        });
    }

    rating.addEventListener('mouseleave', () => render(selectedScore));
    rating.addEventListener('focusout', (event) => {
        if (!rating.contains(event.relatedTarget)) render(selectedScore);
    });

    render(selectedScore);
})();
