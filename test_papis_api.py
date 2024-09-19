import papis.api as pa
import papis.document as pd

def test_get_info():
    libs = pa.get_libraries()
    print(libs)

    docs = pa.get_all_documents_in_lib(libs[0])
    doc = pa.pick_doc(docs)

    print(doc[0].get_info_file())


if __name__ == '__main__':
    test_get_info()
