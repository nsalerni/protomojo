from std.testing import assert_equal, assert_true

from proto import decode, encode
from address_book_pb import AddressBook, Contact


def main() raises:
    var contact = Contact()
    contact.id = 42
    contact.display_name = "Ada Lovelace"
    contact.email = "ada@example.com"
    contact.phone_numbers.append("+1-555-0100")
    contact.phone_numbers.append("+1-555-0101")
    contact.labels["team"] = "computing"
    contact.active = True

    var sent = AddressBook()
    sent.contacts.append(contact^)

    var wire = encode(sent)
    var received = decode[AddressBook](Span(wire))

    assert_equal(len(received.contacts), 1)
    assert_equal(received.contacts[0].id, UInt64(42))
    assert_equal(received.contacts[0].display_name, "Ada Lovelace")
    assert_equal(received.contacts[0].email, "ada@example.com")
    assert_equal(len(received.contacts[0].phone_numbers), 2)
    assert_equal(received.contacts[0].labels["team"], "computing")
    assert_true(received.contacts[0].active)

    print("decoded", len(received.contacts), "contact from", len(wire), "bytes")
