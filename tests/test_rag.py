from apps.support.rag import RAGService, TfidfRetriever, tokenize, load_knowledge_chunks

from .base import BaseAPITest


class RagTests(BaseAPITest):
    def ask(self, user, question):
        return self.call(user, "post", "/api/support/ask/", {"question": question})

    def test_answers_from_knowledge_base(self):
        res = self.ask(self.citizen, "What do I need for police verification?")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sources"][0]["source"], "Police Verification")
        self.assertIn("NID", res.data["answer"])

    def test_passport_renewal(self):
        res = self.ask(self.citizen, "how to renew my passport")
        self.assertEqual(res.data["sources"][0]["source"], "Passport Request")

    def test_status_question_uses_users_own_requests_only(self):
        self.new_request(title="Passport renewal")
        res = self.ask(self.citizen, "What is the status of my request?")
        self.assertIn("Not validated yet", res.data["answer"])
        self.assertIn("Passport renewal", res.data["answer"])
        other = self.ask(self.other, "What is the status of my request?")
        self.assertNotIn("Passport renewal", other.data["answer"])

    def test_various_status_phrasings(self):
        self.new_request(title="Passport renewal")
        for q in ("What is my current status", "where is my request", "any update on my application?", "statuses"):
            res = self.ask(self.citizen, q)
            self.assertNotIn("couldn't find", res.data["answer"], q)
        self.assertIn("Not validated yet", self.ask(self.citizen, "What is my current status").data["answer"])

    def test_personal_question_without_requests_falls_back_to_guides(self):
        res = self.ask(self.other, "What is my current status")
        self.assertEqual(res.status_code, 200)

    def test_unknown_question_falls_back(self):
        res = self.ask(self.citizen, "zxqv blorf wibble")
        self.assertEqual(res.data["sources"], [])
        self.assertIn("couldn't find", res.data["answer"])

    def test_requires_login_and_validates_input(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/support/ask/", {"question": "hi"}, format="json").status_code, 401)
        self.assertEqual(self.ask(self.citizen, "").status_code, 400)

    def test_components_are_swappable(self):
        class Shout:
            def generate(self, question, hits):
                return "HITS=%d" % len(hits)
        service = RAGService(generator=Shout(), user_context=lambda u: [])
        self.assertTrue(service.answer("passport renewal")["answer"].startswith("HITS="))

    def test_tokenizer_and_retriever(self):
        self.assertEqual(tokenize("The Passports"), ["passport"])
        hits = TfidfRetriever(load_knowledge_chunks()).search("missing child report")
        self.assertEqual(hits[0][0].source, "Missing Report")
