from flask import Flask, request, jsonify, render_template
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import ast
import os

# Flask app initialization
app = Flask(__name__)

# File paths
file_path_backend = './data/Sorted_Ngành_Nghề.xlsx'  # Backend data Excel file
file_path_frontend = './data/Book1.xlsx'  # Frontend data Excel file
file_path_family = './data/FamilyFactor.xlsx'

# Load datasets
data_backend = pd.read_excel(file_path_backend)
data_frontend = pd.read_excel(file_path_frontend)
family_data = pd.read_excel(file_path_family)
# Function to clean and process bracketed columns
def clean_brackets(column):
    cleaned_data = []
    for entry in column:
        try:
            cleaned_data.append(" ".join(ast.literal_eval(entry)))
        except (ValueError, SyntaxError):
            cleaned_data.append(str(entry).replace("[", "").replace("]", ""))
    return cleaned_data

# Ensure required columns exist, fill missing columns with empty strings
for col in ['Khả năng và Điểm mạnh', 'Sở thích và Đam mê', 'MBTI', 'Tổ hợp môn']:
    if col not in data_backend.columns:
        print(f"Warning: Column '{col}' is missing in the backend data. Adding empty placeholder.")
        data_backend[col] = ""

# Clean specific columns
data_backend['MAIN STRENGTHS'] = clean_brackets(data_backend['MAIN STRENGTHS'])
data_backend['Khả năng và Điểm mạnh'] = clean_brackets(data_backend['Khả năng và Điểm mạnh'])
data_backend['MAIN INTERESTEDS'] = clean_brackets(data_backend['MAIN INTERESTEDS'])
data_backend['Sở thích và Đam mê'] = clean_brackets(data_backend['Sở thích và Đam mê'])

# Combine relevant columns for TF-IDF processing
data_backend['Combined'] = (
    data_backend['MBTI'].fillna("") + " " +
    data_backend['Tổ hợp môn'].fillna("") + " " +
    data_backend['MAIN STRENGTHS'].fillna("") + " " +
    data_backend['Khả năng và Điểm mạnh'].fillna("") + " " +
    data_backend['MAIN INTERESTEDS'].fillna("") + " " +
    data_backend['Sở thích và Đam mê'].fillna("")
)

# Vectorize the combined data using TF-IDF
tfidf_vectorizer = TfidfVectorizer()
tfidf_matrix = tfidf_vectorizer.fit_transform(data_backend['Combined'])


@app.route('/submit', methods=['POST'])
def submit():
    if request.content_type != 'application/json':
        return jsonify({"error": "Invalid content type"}), 415

    data = request.get_json()
    family_advice = data.get('family_advice', '')
    family_industry_select = data.get('family_industry_select', '')
    family_industry = data.get('family_industry', '')
    financial_influence = data.get('financial_influence', '')

    mbti = data.get('mbti', '').strip().upper()
    subjects = [subject.strip().upper() for subject in data.get('subjects', [])]
    mainstrengths = set(data.get('mainstrengths', []))
    strengths = set(data.get('strengths', []))
    maininterests = set(data.get('maininterests', []))
    interests = set(data.get('interests', []))

    mainstrengths_vector = tfidf_vectorizer.transform([" ".join(mainstrengths)]) if mainstrengths else None
    strengths_vector = tfidf_vectorizer.transform([" ".join(strengths)]) if strengths else None
    maininterests_vector = tfidf_vectorizer.transform([" ".join(maininterests)]) if maininterests else None
    interests_vector = tfidf_vectorizer.transform([" ".join(interests)]) if interests else None

    high_tuition_careers = family_data['Top học phí'].dropna().unique()
    top_social_careers = family_data['Top nghề nghiệp'].dropna().unique()

    suggestions = []
    for i in range(len(data_backend)):
        row = data_backend.iloc[i]
        backend_mbtis = {mbti.strip() for mbti in str(row['MBTI']).split(',')}
        mbti_score = 1.0 if mbti in backend_mbtis else 0.0

        backend_subjects = {subject.strip() for subject in str(row['Tổ hợp môn']).split(',')}
        subjects_score = 1.0 if any(subject in backend_subjects for subject in subjects) else 0.0

        main_strengths_score = cosine_similarity(mainstrengths_vector, tfidf_vectorizer.transform([row['MAIN STRENGTHS']])).flatten()[0] if mainstrengths_vector is not None else 0
        remaining_strengths_score = cosine_similarity(strengths_vector, tfidf_vectorizer.transform([row['Khả năng và Điểm mạnh']])).flatten()[0] if strengths_vector is not None else 0
        strengths_score = main_strengths_score * 0.35 + remaining_strengths_score * 0.65

        main_interests_score = cosine_similarity(maininterests_vector, tfidf_vectorizer.transform([row['MAIN INTERESTEDS']])).flatten()[0] if maininterests_vector is not None else 0
        remaining_interests_score = cosine_similarity(interests_vector, tfidf_vectorizer.transform([row['Sở thích và Đam mê']])).flatten()[0] if interests_vector is not None else 0
        interests_score = main_interests_score * 0.35 + remaining_interests_score * 0.65

        PF_score = mbti_score * 0.2391 + subjects_score * 0.2457 + strengths_score * 0.2609 + interests_score * 0.2543
        family_score = 0.5456
        financial_influence_score = 1 if financial_influence == "Có" else 0

        if financial_influence_score == 1 and row['Ngành'] in high_tuition_careers:
            family_score -= 0.5456

        social_factor_score = 1 if row['Ngành'] in top_social_careers else 0
        final_score = PF_score * 0.5702 + family_score * 0.2936 + social_factor_score * 0.1362

        suggestions.append((row['Ngành'], final_score))

    # Fetch top 10 suggested careers
    suggestions = sorted(suggestions, key=lambda x: x[1], reverse=True)[:10]

    # Match careers with universities and colleges
    final_output = []
    for career, score in suggestions:
        matched_universities = university_data[university_data['Ngành'] == career]['Top trường đại học'].dropna().tolist()
        matched_colleges = university_data[university_data['Ngành'] == career]['Top trường Trường cao đẳng'].dropna().tolist()

        final_output.append({
            "career": career,
            "score": f"{score * 100:.2f}%",
            "universities": matched_universities,
            "colleges": matched_colleges
        })

    return jsonify(final_output), 200



@app.route('/')
def index():
    # Sắp xếp dữ liệu trước khi gửi đến giao diện
    mbti_options = sorted(data_frontend['MBTI'].dropna().unique())
    subject_combination_options = sorted(data_frontend['Tổ hợp môn'].dropna().unique())
    strengths_options = sorted(data_frontend['Khả năng và Điểm mạnh'].dropna().unique())
    interests_options = sorted(data_frontend['Sở thích và Đam mê'].dropna().unique())
    field_options = sorted(data_frontend['Lĩnh vực'].dropna().unique())

    return render_template(
        'index.html',
        mbti_options=mbti_options,
        subject_combination_options=subject_combination_options,
        strengths_options=strengths_options,
        interests_options=interests_options,
        fields=field_options
    )

if __name__ == '__main__':
    print("Starting Flask app...")
    app.run(debug=True)
