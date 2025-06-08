CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    name VARCHAR(100),
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE words (
    id SERIAL PRIMARY KEY,
    english_text VARCHAR(255) NOT NULL,
    translation VARCHAR(255) NOT NULL,
    example TEXT,
    difficulty INT
);

CREATE TABLE user_progress (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    word_english VARCHAR(255) NOT NULL,
    word_translation VARCHAR(255) NOT NULL,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_correct BOOLEAN
);

CREATE TABLE lessons (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    description TEXT
);

CREATE TABLE lesson_words (
    lesson_id INT REFERENCES lessons(id),
    word_id INT REFERENCES words(id),
    PRIMARY KEY (lesson_id, word_id)
);

CREATE TABLE common_words (
    id SERIAL PRIMARY KEY,
    english_text VARCHAR(255) NOT NULL,
    translation VARCHAR(255) NOT NULL,
    example TEXT
);

CREATE TABLE user_words (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    english_text VARCHAR(255) NOT NULL,
    translation VARCHAR(255) NOT NULL,
    example TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, english_text)
);