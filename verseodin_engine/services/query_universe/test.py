from utils import *

def main():
    url = "https://www.merlinai.co/"
    tokens = brand_tokens_from_domain(url)
    print("Brand tokens:", tokens)
    check= is_brand_blog("https://www.merlinai.co/blogs/how-merlin-ai-reduces-project-delays-by-automating-daily-progress-tracking",tokens)
    print(check)

if __name__ == "__main__":
    main()